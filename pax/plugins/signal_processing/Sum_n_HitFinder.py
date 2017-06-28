import numpy as np
import numba

# For diagnostic plotting:
import matplotlib.pyplot as plt
import os

from pax import plugin, datastructure, utils


class FindHits(plugin.TransformPlugin):
    """Finds hits in pulses
    First, the baseline is computed as the mean of the first initial_baseline_samples in the pulse.
    Next, hits are found based on a high and low threshold:
     - A hit starts/ends when it passes the low_threshold
     - A hit has to pass the high_threshold somewhere.

    Thresholds can be set on three different quantities. These are computed per pulse, the highest is used.
    Here high/positive means 'signal like' (i.e. the PMT voltage becomes more negative)

    1) Height over noise threshold
           Options: height_over_noise_high_threshold, height_over_noise_low_threshold
       This threshold operates on the height above baseline / noise level
       The noise level is deteremined in each pulse as
         (<(w - baseline)**2>)**0.5
       with the average running *only* over samples < baseline!

    2) Absolute ADC counts above baseline
           Options: absolute_adc_counts_high_threshold, absolute_adc_counts_low_threshold
       If there is measurable noise in the waveform, you don't want the thresholds to fall to 0 and crash pax.
       This happens for pulses constant on initial_baseline_samples.
       Please use this as a deep fallback only, unless you know what mess you're getting yourself into!

    3) - Height / minimum
           Options: height_over_min_high_threshold, height_over_min_LOW_threshold
       Using this threshold protects you against sudden up & down fluctuations, especially in large pulses
       However, keep in mind that one large downfluctuation will cause a sensitivity loss throughout an entire pulse;
       if you have ZLE off, this may be a bad idea...
       This threshold operates on the (-) height above baseline / height below baseline of the lowest sample in pulse


    Edge cases:

    1) After large peaks the zero-length encoding can fail, making a huge pulse with many hits.
       If more than max_hits_per_pulse hits are found in a pulse, the rest will be ignored.
       If this threshold is set too low, you risk missing some hits in such events.
       If set too high, it will degrade performance. Don't set to infinity, we need to allocate memory for this...

    2) Very high hits (near ADC saturation) sometimes have a long tail. To protect against this, we raise the
       low threshold to a fraction dynamic_low_threshold_coeff of the hit height after a hit has been encountered.
       This is a temporary change for just the remainder of a pulse.
       Also, if the hit height * dynamic_low_threshold_coeff is lower than the low threshold, nothing is changed.

    Diagnostic plot options:
        make_diagnostic_plots can be always, never, tricky cases, no hits, hits only. This controls whether to make
        diagnostic plots showing individual pulses and the hitfinder's interpretation of them. For details on what
        constitutes a tricky case, check the source.
        make_diagnostic_plots_in sets the directory where the diagnostic plots are created.

    Debugging tip:
    If you get an error from one of the numba methods in this plugin (exception from native function blahblah)
    Try commenting the @jit decorators, which will run a slow, pure-python version of the methods,
    allowing you to debug. Don't forget to re-enable the @jit -- otherwise it will run quite slow!
    """

    def startup(self):
        c = self.config

        self.initial_baseline_samples = c.get('initial_baseline_samples', 50)
        self.max_hits_per_pulse = c['max_hits_per_pulse']

        self.make_diagnostic_plots = c.get('make_diagnostic_plots', 'never')
        self.make_diagnostic_plots_in = c.get('make_diagnostic_plots_in', 'small_pf_diagnostic_plots')
        self.sum_n_samples = c.get('sum_n_samples', 20)
        self.sum_start = c.get('sum_start', 200)
        if self.make_diagnostic_plots != 'never':
            if not os.path.exists(self.make_diagnostic_plots_in):
                os.makedirs(self.make_diagnostic_plots_in)

        # Keep track of how many times the "too many hits" warning has been shown
        self.too_many_hits_warnings_shown = 0

    def transform_event(self, event):
        # Allocate numpy arrays to hold numba hitfinder results
        # -1 is a placeholder for values that should never appear (0 would be bad as it often IS a possible value)
        hits_buffer = -1 * np.ones((self.max_hits_per_pulse, 2), dtype=np.int64)
        argmaxes = -1 * np.ones(self.max_hits_per_pulse, dtype=np.int64)
        areas = -1 * np.ones(self.max_hits_per_pulse, dtype=np.float64)
        centers = -1 * np.ones(self.max_hits_per_pulse, dtype=np.float64)

        dt = self.config['sample_duration']

        for pulse_i, pulse in enumerate(event.pulses):
            start = pulse.left
            stop = pulse.right
            channel = pulse.channel
            pmt_gain = self.config['gains'][channel]

            # Retrieve waveform as floats: needed to subtract baseline (which can be in between ADC counts)
            w = pulse.raw_data.astype(np.float64)

            # Subtract reference baseline, invert (so hits point up from baseline)
            # This is convenient so we don't have to reinterpret min, max, etc
            w = self.config['digitizer_reference_baseline'] - w

            pulse.baseline, pulse.noise_sigma, pulse.minimum, pulse.maximum = \
                compute_pulse_properties(w, self.initial_baseline_samples)

            w -= pulse.baseline

            # Don't do hitfinding in dead channels, pulse property computation was enough
            # Could refactor pulse property computation to separate plugin,
            # but that would mean waveform has to be converted to floats twice
            if pmt_gain == 0:
                continue

            # Compute thresholds based on noise level
            high_threshold = max(self.config['height_over_noise_high_threshold'] * pulse.noise_sigma,
                                 self.config['absolute_adc_counts_high_threshold'],
                                 - self.config['height_over_min_high_threshold'] * pulse.minimum)
            low_threshold = max(self.config['height_over_noise_low_threshold'] * pulse.noise_sigma,
                                self.config['absolute_adc_counts_low_threshold'],
                                - self.config['height_over_min_low_threshold'] * pulse.minimum)

            # Call the numba hit finder -- see its docstring for description
            n_hits_found = find_intervals_above_threshold(
                w, high_threshold, low_threshold, hits_buffer,
                dynamic_low_threshold_coeff=self.config['dynamic_low_threshold_coeff'])

            # Only view the part of hits_buffer that contains hits found in this event
            # The rest of hits_buffer contains -1's or stuff from previous pulses
            hits_found = hits_buffer[:n_hits_found]

            # If no hits were found, this is a noise pulse: update the noise pulse count
            if n_hits_found == 0:
                event.noise_pulses_in[channel] += 1
                # Don't 'continue' to the next pulse! There's stuff left to do!
            # Show too-many-hits message if needed
            # This message really should be shown the first few times, as you should be aware how often this occurs
            elif n_hits_found >= self.max_hits_per_pulse:
                if self.too_many_hits_warnings_shown > 3:
                    show_to = self.log.debug
                else:
                    show_to = self.log.info
                show_to("Pulse %s-%s in channel %s has more than %s hits. "
                        "This usually indicates a zero-length encoding breakdown after a very large S2. "
                        "Further hits in this pulse have been ignored." % (start, stop, channel,
                                                                           self.max_hits_per_pulse))
                self.too_many_hits_warnings_shown += 1
                if self.too_many_hits_warnings_shown == 3:
                    self.log.info('Further too-many hit messages will be suppressed!')

            # Compute area, max, and center of each hit in numba
            # Results stored in argmaxes, areas, centers; declared outside loop, see above
            compute_hit_properties(w, hits_found, argmaxes, areas, centers)

            # Store the found hits in the datastructure
            # Convert area, noise_sigma and height from adc counts -> pe
            adc_to_pe = utils.adc_to_pe(self.config, channel)
            noise_sigma_pe = pulse.noise_sigma * adc_to_pe
            for i, hit in enumerate(hits_found):

                # Do sanity checks
                area = areas[i] * adc_to_pe
                sum_start = self.sum_start + i * self.sum_n_samples
                sum_end = sum_start+self.sum_n_samples
                summed_samples = sum(w[sum_start:sum_end]) * adc_to_pe
                center = (centers[i] + start + hit[0]) * dt
                height = w[hit[0] + argmaxes[i]] * adc_to_pe
                left = start + hit[0]
                right = start + hit[1]
                max_idx = start + hit[0] + argmaxes[i]
                if not (0 <= left <= max_idx <= right) \
                   or not (left <= center / dt <= right) \
                   or not (0 <= high_threshold * adc_to_pe <= height <= area):
                    raise RuntimeError("You found a hitfinder bug!\n"
                                       "Current hit %d-%d-%d, in event %s, channel %s, pulse %s.\n"
                                       "Indices in pulse: %s-%s-%s. Pulse bounds: %d-%d.\n"
                                       "Center of gravity at %s.\n"
                                       "Height is %s, noise sigma is %s, threshold at %s.\n"
                                       "Area is %d.\n"
                                       "Please file a bug report!" % (
                                           left, max_idx, right, event.event_number, channel, pulse_i,
                                           hit[0], hit[0] + argmaxes[i], hit[1], start, stop,
                                           center,
                                           height, noise_sigma_pe, high_threshold * adc_to_pe,
                                           area))

                # If the pulse reached saturation, we should also count the saturation in each hit
                # This is rare enough that it doesn't need to be in numba
                n_saturated = 0
                if pulse.maximum - pulse.baseline >= self.config['digitizer_reference_baseline']:
                    n_saturated = np.count_nonzero(w[hit[0]:hit[1] + 1] >=
                                                   self.config['digitizer_reference_baseline'] - pulse.baseline)

                # Store the hit
                # int's need to be cast to avoid weird numpy types in our datastructure
                # Type checking in data_model takes care of this, but if someone ever turns off type checking
                # (e.g. because they want a x2 speed boost in loading data) I don't want them to get
                # strange BSON encoding errors (bson.errors.InvalidDocument: Cannot encode object: 4332)
                event.all_hits.append(datastructure.Hit({
                    'channel':             channel,
                    'left':                int(left),
                    'index_of_maximum':    int(max_idx),
                    'center':              center,
                    'right':               int(right),
                    'area':                area,
                    'height':              height,
                    'noise_sigma':         noise_sigma_pe,
                    'found_in_pulse':      pulse_i,
                    'n_saturated':         n_saturated,
                    'summed_samples':      summed_samples,
                }))

            # Diagnostic plotting
            # Difficult to move to separate plugin:
            # would have to re-group hits by pulse, move settings like threshold to DEFAULT or use hack...

            # Do we need to show this pulse? If not: continue
            if self.make_diagnostic_plots == 'never':
                continue
            elif self.make_diagnostic_plots == 'tricky cases':
                # Always show pulse if noise level is very high
                if noise_sigma_pe < 0.5:
                    if len(hits_found) == 0:
                        # Show pulse if it nearly went over threshold
                        if not pulse.maximum > 0.8 * high_threshold:
                            continue
                    else:
                        # Show pulse if any of its hit nearly didn't go over threshold
                        if not any([event.all_hits[-(i+1)].height < 1.2 * high_threshold * adc_to_pe
                                   for i in range(len(hits_found))]):
                            continue
            elif self.make_diagnostic_plots == 'no hits':
                if len(hits_found) != 0:
                    continue
            elif self.make_diagnostic_plots == 'hits only':
                if len(hits_found) == 0:
                    continue
            elif self.make_diagnostic_plots == 'saturated':
                if not pulse.maximum - pulse.baseline >= self.config['digitizer_reference_baseline']:
                    continue
            else:
                if self.make_diagnostic_plots != 'always':
                    raise ValueError("Invalid make_diagnostic_plots option: %s!" % self.make_diagnostic_plots)

            # Setup the twin-y-axis plot
            fig, ax1 = plt.subplots(figsize=(10, 7))
            ax2 = ax1.twinx()
            ax1.set_xlabel("Sample number (%s ns)" % event.sample_duration)
            ax1.set_ylabel("ADC counts above baseline")
            ax2.set_ylabel("pe / sample")

            # Plot the signal and noise levels
            ax1.plot(w, drawstyle='steps-mid', label='Data')
            ax1.plot(np.ones_like(w) * high_threshold, '--', label='Threshold', color='red')
            ax1.plot(np.ones_like(w) * pulse.noise_sigma, ':', label='Noise level', color='gray')
            ax1.plot(np.ones_like(w) * pulse.minimum, '--', label='Minimum', color='orange')
            ax1.plot(np.ones_like(w) * low_threshold, '--', label='Boundary threshold', color='green')

            # Mark the hit ranges & center of gravity point
            for hit_i, hit in enumerate(hits_found):
                ax1.axvspan(hit[0] - 0.5, hit[1] + 0.5, color='red', alpha=0.2)
                # Remember: array 'centers' is still in samples since start of hit...
                ax1.axvline([centers[hit_i] + hit[0]], linestyle=':', color='gray')

            # Make sure the y-scales match
            ax2.set_ylim(ax1.get_ylim()[0] * adc_to_pe, ax1.get_ylim()[1] * adc_to_pe)

            # Finish the plot, save, close
            leg = ax1.legend()
            leg.get_frame().set_alpha(0.5)
            bla = (event.event_number, start, stop, channel)
            plt.title('Event %s, pulse %d-%d, Channel %d' % bla)
            plt.savefig(os.path.join(self.make_diagnostic_plots_in,
                                     'event%04d_pulse%05d-%05d_ch%03d.png' % bla))
            plt.close()

        return event


@numba.jit(nopython=True)
def find_intervals_above_threshold(w, high_threshold, low_threshold, result_buffer, dynamic_low_threshold_coeff=0):
    """Fills result_buffer with l, r bounds of intervals in w > low_threshold which exceed high_threshold somewhere
        result_buffer: numpy N*2 array of ints, will be filled by function.
    Returns: number of intervals found
    Will stop search after N intervals are found, with N the length of result_buffer.
    Boundary indices are inclusive, i.e. the right index is the last index which was still above low_threshold
    """
    in_candidate_interval = False
    current_interval_passed_test = False
    current_interval = 0
    result_buffer_size = len(result_buffer)
    last_index_in_w = len(w) - 1
    current_candidate_interval_start = -1

    for i, x in enumerate(w):

        if not in_candidate_interval and x > low_threshold:
            # Start of candidate interval
            in_candidate_interval = True
            current_candidate_interval_start = i

        # This must be if, not else: an interval can cross high_threshold in start sample
        if in_candidate_interval:

            if x > high_threshold:
                current_interval_passed_test = True
                # Raise lower threshold to a fraction of the hit height
                # This helps against tails (due to amplifiers?) for REALLY high hits
                low_threshold = max(low_threshold, dynamic_low_threshold_coeff*x)

            if x <= low_threshold or i == last_index_in_w:

                # End of candidate interval
                in_candidate_interval = False

                if current_interval_passed_test:
                    # We've found a new interval!

                    # The interval ended just before this index
                    # unless, of course, we ended ONLY BECAUSE this is the last index
                    itv_end = i-1 if x <= low_threshold else i

                    # Add to result buffer
                    result_buffer[current_interval, 0] = current_candidate_interval_start
                    result_buffer[current_interval, 1] = itv_end

                    # Prepare for the next interval
                    current_interval += 1
                    current_interval_passed_test = False

                    if current_interval == result_buffer_size:
                        break

    # Return number of hits found
    # One day numba may have crashed here: not sure if it is int32 or int64...
    return current_interval


@numba.jit(nopython=True)
def compute_hit_properties(w, raw_hits, argmaxes, areas, centers):
    """Finds argmax, area and center of gravity of hits in w indicated by (l, r) bounds in raw_hits.
    raw_hits should be a numpy array of (left, right) bounds (inclusive)
    Other arguments are numpy arrays which will be filled with results.
    centers, argmaxes are returned in samples right of hit start -- you probably want to convert this!
    Returns nothing
    """
    for hit_i in range(len(raw_hits)):
        current_max = -999.9
        current_argmax = -1
        current_area = 0.0
        current_center = 0.0
        for i, x in enumerate(w[raw_hits[hit_i, 0]:raw_hits[hit_i, 1]+1]):
            if x > current_max:
                current_max = x
                current_argmax = i
            current_area += x
            current_center += i * x
        argmaxes[hit_i] = current_argmax
        areas[hit_i] = current_area
        centers[hit_i] = current_center / current_area


@numba.jit(nopython=True)
def compute_pulse_properties(w, initial_baseline_samples):
    """Compute basic pulse properties quickly
    :param w: Raw pulse waveform in ADC counts
    :param initial_baseline_samples: number of samples at start of pulse to use for baseline computation
    :return: (baseline, noise_sigma, min, max);
      min and max are relative to baseline
      noise_sigma is the std of samples below baseline
    Does not modify w. Does not assume anything about inversion of w!!
    """

    # First compute baseline
    baseline = 0.0
    initial_baseline_samples = min(initial_baseline_samples, len(w))
    for x in w[:initial_baseline_samples]:
        baseline += x
    baseline /= initial_baseline_samples

    # Now compute mean, noise, and min
    n = 0           # Running count of samples included in noise sample
    m2 = 0          # Running sum of squares of differences from the baseline
    max_a = -1.0e6  # Running max amplitude
    min_a = 1.0e6   # Running min amplitude

    for x in w:
        if x > max_a:
            max_a = x
        if x < min_a:
            min_a = x
        if x < baseline:
            delta = x - baseline
            n += 1
            m2 += delta*(x-baseline)

    if n == 0:
        # Should only happen if w = baseline everywhere
        noise = 0
    else:
        noise = (m2/n)**0.5

    return baseline, noise, min_a - baseline, max_a - baseline
