import numba
import numpy as np

from pax import units
from pax.datastructure import Hit


@numba.jit(numba.int64[:](numba.from_dtype(Hit.get_dtype())[:]),
           nopython=True, cache=True)
def gaps_between_hits(hits):
    """Return array of gaps between hits: a hit's 'gap' is the # of samples before that hit free of other hits.
    The gap of the first hit is 0 by definition.
    Hits should already be sorted by left boundary; we'll check this and throw an error if not.
    """
    n_hits = len(hits)
    gaps = np.zeros(n_hits, dtype=np.int64)
    if n_hits == 0:
        return gaps
    # Keep a running right boundary
    boundary = hits[0].right
    last_left = hits[0].left
    for i, hit in enumerate(hits[1:]):
        gaps[i + 1] = max(0, hit.left - boundary - 1)
        boundary = max(hit.right, boundary)
        if hit.left < last_left:
            raise ValueError("Hits should be sorted by left boundary!")
        last_left = hit.left
    return gaps


def count_hits_per_channel(peak, config, weights=None):
    return np.bincount(peak.hits['channel'], minlength=config['n_channels'], weights=weights)


def adc_to_pe(config, channel, use_reference_gain=False, use_reference_gain_if_zero=False):
    """Gives the conversion factor from ADC counts above baseline to pe/bin
    Use as: w_in_pe_bin = adc_to_pe(config, channel) * w_in_adc_above_baseline
      - config should be a configuration dictionary (self.config in a pax plugin)
      - If use_reference_gain is True, will always use config.get('pmt_reference_gain', 2e6) rather than the pmt gain
      - If use_reference_gain_if_zero=True will do the above only if channel gain is 0.
    If neither of these are true, and gain is 0, will return 0.
    """
    c = config
    adc_to_e = c['sample_duration'] * c['digitizer_voltage_range'] / (
        2 ** (c['digitizer_bits']) *
        c['pmt_circuit_load_resistor'] *
        c['external_amplification'] *
        units.electron_charge)
    pmt_gain = c['gains'][channel]
    if use_reference_gain_if_zero and pmt_gain == 0 or use_reference_gain:
        pmt_gain = c.get('pmt_reference_gain', 2e6)
    if pmt_gain == 0:
        return 0
    return adc_to_e / pmt_gain


def get_detector_by_channel(config):
    """Return a channel -> detector lookup dictionary from a configuration"""
    detector_by_channel = {}
    for name, chs in config['channels_in_detector'].items():
        for ch in chs:
            detector_by_channel[ch] = name
    return detector_by_channel


def cluster_by_diff(x, diff_threshold, return_indices=False):
    """Returns list of lists of indices of clusters in x,
    making cluster boundaries whenever values are >= threshold apart.
    """
    x = sorted(x)
    if len(x) == 0:
        return []
    clusters = []
    current_cluster = []
    previous_t = x[0]
    for i, t in enumerate(x):
        if t - previous_t > diff_threshold:
            clusters.append(current_cluster)
            current_cluster = []
        current_cluster.append(i if return_indices else t)
        previous_t = t
    clusters.append(current_cluster)
    return clusters
    # Numpy solution below appears to make processor run slower!
    # x.sort()
    # if not isinstance(x, np.ndarray):
    #     x = np.array(x)
    # split_indices = np.where(np.diff(x) >= diff_threshold)[0] + 1
    # if return_indices:
    #     return np.split(np.arange(len(x)), split_indices)
    # else:
    #     return np.split(x, split_indices)
