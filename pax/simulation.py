"""
Waveform simulator ("FaX") - physics backend
There is no I/O stuff here, all that is in the WaveformSimulator plugins
"""

import numpy as np
import math
import time

import logging
log = logging.getLogger('SimulationCore')
from pax import units, dsputils, datastructure


##
#  Configuration handling
##
global config

def init_config(config_to_init):
    global config
    config = config_to_init
    # Should we repeat events?
    if not 'event_repetitions' in config:
        config['event_repetitions'] = 1

    efield = (config['drift_field']/(units.V/units.cm))

    # Primary excimer fraction from Nest Version 098
    # See G4S1Light.cc line 298
    density = config['liquid_density'] / (units.g / units.cm**3)
    excfrac = 0.4-0.11131*density-0.0026651*density**2                   # primary / secondary excimers
    excfrac = 1/(1+excfrac)                                              # primary / all excimers
    excfrac /= 1-(1-excfrac)*(1-config['s1_ER_recombination_fraction'])  # primary / all excimers that produce a photon
    config['s1_ER_primary_excimer_fraction'] = excfrac
    log.debug('Inferred s1_ER_primary_excimer_fraction %s' % excfrac)

    # Recombination time from NEST 2014
    # 3.5 seems fishy, they fit an exponential to data, but in the code they use a non-exponential distribution...
    config['s1_ER_recombination_time'] = 3.5/0.18 * (1/20 + 0.41) * math.exp(-0.009*efield)
    log.debug('Inferred s1_ER_recombination_time %s ns' % config['s1_ER_recombination_time'])

    # How large is the PMT waveform matrix we will we have to produce?
    config['all_pmts'] = list(config['pmts_top'] | config['pmts_bottom'])

    # Which channels stand to recieve any photons?
    # TODO: In XENON100, channel 0 WILL receive photons unless magically_avoid_dead_pmts=True
    # To prevent this, subtract 0 from channel_for_photons. But don't do that for XENON1T!!
    channels_for_photons = list(config['pmts_top'] | config['pmts_bottom'])
    if config.get('magically_avoid_dead_pmts', False):
        channels_for_photons = [ch for ch in channels_for_photons if config['gains'][ch] > 0]
    if config.get('magically_avoid_s1_excluded_pmts', False):
        channels_for_photons = [ch for ch in channels_for_photons if not ch in config['pmts_excluded_for_s1']]
    config['channels_for_photons'] = channels_for_photons

    # Determine sensible length of a pmt pulse to simulate
    dt = config['digitizer_t_resolution']
    config['samples_before_pulse_center'] = math.ceil(
        config['pulse_width_cutoff'] * config['pmt_rise_time'] / dt
    )
    config['samples_after_pulse_center'] = math.ceil(
        config['pulse_width_cutoff'] * config['pmt_fall_time'] / dt
    )
    log.debug('Simulating %s samples before and %s samples after PMT pulse centers.')

    # Padding before & after each pulse/peak/photon-cluster/whatever-you-call-it
    if not 'pad_after' in config:
        config['pad_after'] = 30 * dt + config['samples_after_pulse_center']
    if not 'pad_before' in config:
        config['pad_before'] = (
            # 10 + Baseline bins
            50 * dt
            # Protection against early pre-peak rise
            + config['samples_after_pulse_center']
            # Protection against pulses arriving earlier than expected due
            # to tail of TTS distribution
            + 10 * config['pmt_transit_time_spread']
            - config['pmt_transit_time_mean']
        )
        log.debug('Determined padding at %s ns' % config['pad_before'])

    return config


@np.vectorize
def exp_pulse(t, q, tr, tf):
    """Integrated current (i.e. charge) of a single-pe PMT pulse centered at t=0
    Assumes an exponential rise and fall waveform model
    :param t:   Time to integrate up to
    :param q:   Total charge in the pulse
    :param tr:  Rise time
    :param tf:  Fall time
    :return: Float, charge deposited up to t
    """
    c = 0.45512  # 1/(ln(10)-ln(10/9))
    if t < 0:
        return q / (tr + tf) * (tr * math.exp(t / (c * tr)))
    else:
        return q / (tr + tf) * (tr + tf * (1 - math.exp(-t / (c * tf))))


def s2_electrons(electrons_generated=None, z=0., t=0.):
    """Return a list of electron arrival times in the ELR region caused by an S2 process.

        electrons             -   total # of drift electrons generated at the interaction site
        t                     -   Time at which the original energy deposition occurred.
        z                     -   Depth below the GATE mesh where the interaction occurs.
    As usual, all units in the same system used by pax (if you specify raw values: ns, cm)
    """

    if z < 0:
        log.warning("Unphysical depth: %s cm below gate. Not generating S2." % z)
        return []
    log.debug("Creating an s2 from %s electrons..." % electrons_generated)

    # Average drift time, taking faster drift velocity after gate into account
    drift_time_mean = z / config['drift_velocity_liquid'] + \
        (config['gate_to_anode_distance'] - config['elr_gas_gap_length']) \
        / config['drift_velocity_liquid_above_gate']

    # Diffusion model from Sorensen 2011
    drift_time_stdev = math.sqrt(2 * config['diffusion_constant_liquid'] * drift_time_mean)
    drift_time_stdev /= config['drift_velocity_liquid']

    # Absorb electrons during the drift
    electrons_seen = np.random.binomial(
        n= electrons_generated,
        p= config['electron_extraction_yield']
           * math.exp(- drift_time_mean / config['electron_lifetime_liquid'])
    )
    log.debug("    %s electrons survive the drift." % electrons_generated)

    # Calculate electron arrival times in the ELR region
    e_arrival_times = t + np.random.exponential(config['electron_trapping_time'], electrons_seen)
    if drift_time_stdev:
        e_arrival_times += np.random.normal(drift_time_mean, drift_time_stdev, electrons_seen)
    return e_arrival_times


def s1_photons(n_photons, recoil_type, t=0.):
    """
    Returns a list of photon production times caused by an S1 process.

    """
    # Apply detection efficiency
    log.debug("Creating an s1 from %s photons..." % n_photons)
    n_photons = np.random.binomial(n=n_photons, p=config['s1_detection_efficiency'])
    log.debug("    %s photons are detected." % n_photons)
    if n_photons == 0:
        return np.array([])

    if recoil_type == 'ER':

        # How many of these are primary excimers? Others arise through recombination.
        n_primaries = np.random.binomial(n=n_photons, p=config['s1_ER_primary_excimer_fraction'])

        primary_timings = singlet_triplet_delays(
            np.zeros(n_primaries),  # No recombination delay for primary excimers
            t1=config['singlet_lifetime_liquid'],
            t3=config['triplet_lifetime_liquid'],
            singlet_ratio=config['s1_ER_primary_singlet_fraction']
        )

        # Correct for the recombination time
        # For the non-exponential distribution: see Kubota 1979, solve eqn 2 for n/n0.
        # Alternatively, see Nest V098 source code G4S1Light.cc line 948
        secondary_timings = config['s1_ER_recombination_time']\
                            * (-1 + 1/np.random.uniform(0, 1, n_photons-n_primaries))
        secondary_timings = np.clip(secondary_timings, 0, config['maximum_recombination_time'])
        # Handle singlet/ triplet decays as before
        secondary_timings += singlet_triplet_delays(
            secondary_timings,
            t1=config['singlet_lifetime_liquid'],
            t3=config['triplet_lifetime_liquid'],
            singlet_ratio=config['s1_ER_secondary_singlet_fraction']
        )

        timings = np.concatenate((primary_timings, secondary_timings))

    elif recoil_type == 'NR':

        # Neglible recombination time, same singlet/triplet ratio for primary & secondary excimers
        # Hence, we don't care about primary & secondary excimers at all:
        timings = singlet_triplet_delays(
            np.zeros(n_photons),
            t1=config['singlet_lifetime_liquid'],
            t3=config['triplet_lifetime_liquid'],
            singlet_ratio=config['s1_NR_singlet_fraction']
        )

    else:
        raise ValueError('Recoil type must be ER or NR, not %s' % type)

    return timings + t * np.ones(len(timings))


def s2_scintillation(electron_arrival_times):
    """
    Given a list of electron arrival times, returns photon production times
    """

    # How many photons does each electron make?
    # TODO: xy correction!
    photons_produced = np.random.poisson(
        config['s2_secondary_sc_gain_density'] * config['elr_gas_gap_length'],
        len(electron_arrival_times)
    )
    total_photons = np.sum(photons_produced)
    log.debug("    %s scintillation photons will be detected." % total_photons)
    if total_photons == 0:
        return np.array([])

    # Find the photon production times
    # Assume luminescence probability ~ electric field
    s2_pe_times = np.concatenate([
        t0 + get_luminescence_positions(photons_produced[i]) / config['drift_velocity_gas']
        for i, t0 in enumerate(electron_arrival_times)
    ])

    # Account for singlet/triplet excimer decay times
    return singlet_triplet_delays(
        s2_pe_times,
        t1=config['singlet_lifetime_gas'],
        t3=config['triplet_lifetime_gas'],
        singlet_ratio=config['singlet_fraction_gas']
    )


def singlet_triplet_delays(times, t1, t3, singlet_ratio):
    """
    Given a list of eximer formation times, returns excimer decay times.
        t1            - singlet state lifetime
        t3            - triplet state lifetime
        singlet_ratio - fraction of excimers that become singlets
                        (NOT the ratio of singlets/triplets!)
    """
    n_singlets = np.random.binomial(n=len(times), p=singlet_ratio)
    return times + np.concatenate([
        np.random.exponential(t1, n_singlets),
        np.random.exponential(t3, len(times) - n_singlets)
    ])


def get_luminescence_positions(n):
    """Sample luminescence positions in the ELR, using a mixed wire-dominated / uniform field"""
    # TODO: could gain performance here I think
    x = np.random.uniform(0, 1, n)
    l = config['elr_gas_gap_length']
    wire_par = config['wire_field_parameter']
    rm = config['anode_mesh_pitch'] * wire_par
    rw = config['anode_wire_radius']
    if wire_par == 0:
        return x * l
    totalArea = l + rm * (math.log(rm / rw) - 1)
    relA_wd_region = rm * math.log(rm / rw) / totalArea
    # This is a bit slower, not much though:
    # return np.array([
    #     (l - np.exp(xi * totalArea / rm) * rw)
    #     if xi < relA_wd_region
    #     else l - (xi * totalArea + rm * (1 - math.log(rm / rw)))
    #     for xi in x
    # ])
    result = np.zeros(n)
    x_in_relA_wd_region = x < relA_wd_region
    result[x_in_relA_wd_region] = (l - np.exp(x[x < relA_wd_region] * totalArea / rm) * rw)
    result[-x_in_relA_wd_region] = l - (x[-x_in_relA_wd_region] * totalArea + rm * (1 - math.log(rm / rw)))
    return result

class SimulatedHitpattern(object):

    def __init__(self, photon_timings):
        # TODO: specify x, y, z, let photon distribution depend on it

        # Correct for PMT TTS
        photon_timings += np.random.normal(
             config['pmt_transit_time_mean'],
             config['pmt_transit_time_spread'],
             len(photon_timings)
        )

        # The number of pmts which can receive a photon
        ch_for_photons = config['channels_for_photons']
        n_pmts = len(ch_for_photons)

        # First shuffle all timings in the array, so channel 1 doesn't always get the first photon
        np.random.shuffle(photon_timings)

        # Now generate n_pmts integers < n_pmts to denote the splitting points
        # TODO: think carefully about these +1 and -1's Without the +1 S1sClose failed
        split_points = np.sort(np.random.randint(0, len(photon_timings)+1, n_pmts-1))

        # Split the array according to the split points
        # numpy correctly inserts empty arrays if a split point occurs twice if split_points is sorted
        photons_per_channel = np.split(photon_timings, split_points)

        #assert sum(list(map(len, photons_per_channel))) == len(photon_timings)

        # Merge the result in a dictionary, which we return
        # TODO: zip can probably do this faster!
        self.arrival_times_per_channel = {ch_for_photons[i] : photons_per_channel[i] for i in range(n_pmts)}

        # Add the minimum and maximum times, and number of times
        # hitlist_to_waveforms would have to go through weird flattening stuff to determine these
        self.min = min(photon_timings)
        self.max = max(photon_timings)
        self.n_photons = len(photon_timings)

    def __add__(self, other):
        # print("add called self=%s, other=%s" % (type(self), type(other)))
        self.min = min(self.min, other.min)
        self.max = max(self.max, other.max)
        self.n_photons = self.n_photons + other.n_photons
        contributing_channels = set(self.arrival_times_per_channel.keys()) | set(other.arrival_times_per_channel.keys())
        self.arrival_times_per_channel = {
            ch: np.concatenate((
                self.arrival_times_per_channel.get(ch,  np.array([])),
                other.arrival_times_per_channel.get(ch, np.array([]))
            ))
            for ch in contributing_channels
        }
        return self

    def __radd__(self, other):
        # print("radd called self=%s, other=%s" % (type(self), type(other)))
        if other is 0:
            # Apparently sum() starts trying to add stuff to 0...
            return self
        self.__add__(other)


def pmt_pulse_current(gain, offset=0):
    # Rounds offset to nearest pmt_pulse_time_rounding so we can exploit caching
    return gain * pmt_pulse_current_raw(
        config['pmt_pulse_time_rounding']*round(offset/config['pmt_pulse_time_rounding'])
    )

class memoize:
    # from http://avinashv.net/2008/04/python-decorators-syntactic-sugar/
    def __init__(self, function):
        self.function = function
        self.memoized = {}

    def __call__(self, *args):
        try:
            return self.memoized[args]
        except KeyError:
            self.memoized[args] = self.function(*args)
            return self.memoized[args]

@memoize
def pmt_pulse_current_raw(offset):
    dt = config['digitizer_t_resolution']
    return np.diff(exp_pulse(
        np.linspace(
            - offset - config['samples_before_pulse_center'] * dt,
            - offset + config['samples_after_pulse_center']  * dt,
            1 + config['samples_after_pulse_center'] + config['samples_before_pulse_center']),
        units.electron_charge,
        config['pmt_rise_time'],
        config['pmt_fall_time']
    )) / dt

def to_pax_event(hitpattern):
    """Simulate PMT response to a hitpattern of photons
    Returns None if you pass a hitlist without any hits
    returns start_time (in units, ie ns), pmt waveform matrix
    """
    if not isinstance(hitpattern, SimulatedHitpattern):
        raise ValueError("to_pax_event takes an instance of SimulatedHitpattern, you gave a %s." % type(hitpattern))

    log.debug("Now performing hitlist to waveform conversion for %s photons" % hitpattern.n_photons)
    # TODO: Account for random initial digitizer state  wrt interaction?
    # Where?

    # Convenience variables
    dt = config['digitizer_t_resolution']
    dV = config['digitizer_voltage_range'] / 2 ** (config['digitizer_bits'])


    # Build waveform channel by channel
    #pmt_waveforms = np.zeros((len(config['all_pmts']), n_samples), dtype=np.int16)
    occurrences = {}
    for channel, photon_detection_times in hitpattern.arrival_times_per_channel.items():
        photon_detection_times = np.array(photon_detection_times)

        if len(photon_detection_times) == 0:
            continue  # No photons in this channel

        occurrences[channel] = []

        #  Add padding, sort (eh.. or were we already sorted? and is sorting necessary at all??)
        all_pmt_pulse_centers = np.sort(photon_detection_times + config['event_padding'])

        for pmt_pulse_centers in dsputils.split_by_separation(all_pmt_pulse_centers, 2 * config['zle_padding']):

            # Build the waveform pulse by pulse (bin by bin was slow, hope this
            # is faster)

            # Compute offset & center index for each pe-pulse
            pmt_pulse_centers = np.array(pmt_pulse_centers)
            offsets = pmt_pulse_centers % dt
            center_index = (pmt_pulse_centers - offsets) / dt   # Absolute index in waveform of pe-pulse center

            start_index = min(center_index) - int(config['zle_padding']/dt)
            end_index =   max(center_index) + int(config['zle_padding']/dt)
            occurrence_length = end_index - start_index + 1

            current_wave = np.zeros(occurrence_length)

            if len(center_index) > config['use_simplified_simulator_from']:

                #TODO: Is this actually faster still? Should check!

                # Start with a delta function single photon pulse, then convolve with one actual single-photon pulse
                # This effectively assumes photons always arrive at the start of a digitizer t-bin, but is much faster

                # Division by dt necessary for charge -> current

                unique, counts = np.unique(center_index - start_index, return_counts=True)
                unique = unique.astype(np.int)
                current_wave[unique] = counts * config['gains'][channel] * units.electron_charge / dt

                # Previous, slow implementation
                # pulse_counts = Counter(center_index)
                # print(pulse_counts)
                # current_wave2 = np.array([pulse_counts[n] for n in range(n_samples)]) \
                #                * config['gains'][channel] * units.electron_charge / dt

                # Calculate a normalized pmt pulse, for use in convolution later (only
                # for large peaks)
                normalized_pulse = pmt_pulse_current(gain=1)
                normalized_pulse /= np.sum(normalized_pulse)
                current_wave = np.convolve(current_wave, normalized_pulse, mode='same')

            else:

                # Do the full, slower simulation for each single-photon pulse
                for i, _ in enumerate(pmt_pulse_centers):

                    # Add some current for this photon pulse
                    # Compute the integrated pmt pulse at various samples, then
                    # do their diffs/dt
                    generated_pulse = pmt_pulse_current(
                        # Really a Poisson (although mean is so high it is very
                        # close to a Gauss)
                        # TODO: what are you smoking? Add proper distribution!
                        gain=np.random.poisson(config['gains'][channel]),
                        offset=offsets[i]
                    )

                    # +1 due to np.diff in pmt_pulse_current   #????
                    left_index = center_index[i]    - start_index - int(config['samples_before_pulse_center']) + 1
                    righter_index = center_index[i] - start_index + int(config['samples_after_pulse_center'])  + 1

                    # Debugging stuff
                    if len(generated_pulse) != righter_index - left_index:
                        raise RuntimeError("Generated pulse is %s samples long, can't be inserted between %s and %s" % (
                                len(generated_pulse), left_index, righter_index))

                    if left_index <0 :
                        raise RuntimeError("Invalid left index %s: can't be negative!" % left_index)

                    if righter_index >= len(current_wave) :
                        raise RuntimeError("Invalid right index %s: can't be longer than length of wave (%s)!" % (
                            righter_index, len(current_wave)))

                    current_wave[left_index : righter_index] += generated_pulse

            # Add white noise current
            if config['white_noise_sigma'] is not None:
                # / dt is for charge -> current conversion, as in pmt_pulse_current
                current_wave += np.random.normal(0, config['white_noise_sigma'] * config['gains'][channel] / dt,
                                                 len(current_wave))

            # Convert current to digitizer count (should I trunc, ceil or floor?) and store
            # Don't baseline correct, clip or flip down here, we do that at the
            # very end when all signals are combined
            temp = config['digitizer_baseline'] - np.trunc(
                config['pmt_circuit_load_resistor']
                * config['external_amplification'] / dV
                * current_wave
            )
            temp = np.clip(temp, 0, 2 ** (config['digitizer_bits']))
            occurrences[channel].append((start_index, temp.astype(np.int16)))

    if len(occurrences) == 0:
        return None
    event = datastructure.Event()
    event.start_time = int(time.time() * units.s)
    event.stop_time = int(event.start_time) + int(hitpattern.max + 2*config['event_padding'])
    log.debug("Simulated event is %s samples long. Max pulse center at %s ns." %
              (event.length(), max(all_pmt_pulse_centers)))
    event.sample_duration = dt
    event.occurrences = occurrences
    return event



# This is probably in some standard library...
def flatten(l):
    return [item for sublist in l for item in sublist]