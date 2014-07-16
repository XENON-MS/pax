from pax import plugin, units
import numpy as np

# decision: none: accept, string: reject, string specifies reason


def is_s2(peak):
    return peak['peak_type'] in ('large_s2', 'small_s2')


class PeakPruner(plugin.TransformPlugin):

    def __init__(self, config):
        plugin.TransformPlugin.__init__(self, config)

    def transform_event(self, event):
        for peak_index, p in enumerate(event['peaks']):
            #If this is the first peak pruner, we have to set up some values
            if not 'rejected' in p:
                p['rejected'] = False
                p['rejection_reason'] = None
                p['rejected_by'] = None
            #If peak has been rejected earlier, we don't have to test it
            #In the future we may want to disable this to test how the prunings depend on each other
            if p['rejected']:
                continue
            #Child class has to define decide_peak
            decision = self.decide_peak(p, event, peak_index)
            #None means accept the peak. Anything else is a rejection reason.
            if decision != None:
                p['rejected'] = True
                p['rejection_reason'] = decision
                p['rejected_by'] = str(self.__class__.__name__)
        return event

    def decide_peak(self, peak, event, peak_index):
        raise NotImplementedError("This peak pruner forgot to implement decide_peak...")


class PruneNonIsolatedPeaks(PeakPruner):
    #mean of test_before samples before interval must be less than before_to_height_ratio_max times the maximum value in the interval
    #Same for test_after
    #NB: tests the PREPEAK, not the actual peak!!! (XeRawDP behaviour)

    def __init__(self, config):
        PeakPruner.__init__(self, config)
        #These should be in configuration...
        self.settings = {
            'test_before' : {'s1': 50, 'large_s2': 21, 'small_s2': 10},
            'test_after'  : {'s1': 10, 'large_s2': 21, 'small_s2': 10},
            'before_to_height_ratio_max' : {'s1': 0.01, 'large_s2': 0.05, 'small_s2': 0.05},
            'after_to_height_ratio_max'  : {'s1': 0.04, 'large_s2': 0.05, 'small_s2': 0.05}
        }
        
    def decide_peak(self, peak, event, peak_index):
        #Find which settings to use for this type of peak
        settings = {}
        for settingname, settingvalue in self.settings.items():
            settings[settingname] = self.settings[settingname][peak['peak_type']]
        signal = event['processed_waveforms']['top_and_bottom']
        #Calculate before_mean and after_mean
        assert not 'before_mean' in peak    #Fails if you run the plugin twice!
        peak['before_mean'] = np.mean(
            signal[max(0, peak['prepeak_left'] - settings['test_before']): peak['prepeak_left']])
        peak['after_mean'] = np.mean(
            signal[peak['prepeak_right']: min(len(signal), peak['prepeak_right'] + settings['test_after'])])
        #Do the testing
        if peak['before_mean'] > settings['before_to_height_ratio_max'] * peak['height']:
            return '%s samples before peak contain stuff (mean %s, which is more than %s (%s x peak height))' % (settings['test_before'], peak['before_mean'], settings['before_to_height_ratio_max'] * peak['height'], settings['before_to_height_ratio_max'])
        if peak['after_mean'] > settings['after_to_height_ratio_max'] * peak['height']:
            return '%s samples after peak contain stuff (mean %s, which is more than %s (%s x peak height))' % (settings['test_after'], peak['after_mean'], settings['after_to_height_ratio_max'] * peak['height'], settings['after_to_height_ratio_max'])
        return None
                   
    
        
class PruneWideS1s(PeakPruner):

    def __init__(self, config):
        PeakPruner.__init__(self, config)

    def decide_peak(self, peak, event, peak_index):
        if peak['peak_type'] != 's1':
            return None
        fwqm = peak['top_and_bottom']['fwqm']
        treshold = 0.5 * units.us
        if fwqm > treshold:
            return 'S1 FWQM is %s us, higher than maximum %s us.' % (fwqm / units.us, treshold / units.us)
        return None

        
class PruneWideShallowS2s(PeakPruner):
    def __init__(self, config):
        PeakPruner.__init__(self, config)
        
    def decide_peak(self, peak, event, peak_index):
        if str(peak['peak_type']) != 'small_s2': return None
        treshold = 0.062451 #1 mV/bin = 0.1 mV/ns
        peakwidth = (peak['right'] - peak['left'])/units.ns
        ratio = peak['top_and_bottom']['height'] / peakwidth
        if ratio > treshold:
            return 'Max/width ratio %s is higher than %s' % (ratio, treshold)
        return None
        
class PruneS1sWithNearbyNegativeExcursions(PeakPruner):
    def __init__(self, config):
        PeakPruner.__init__(self, config)
        
    def decide_peak(self, p, event, peak_index):
        if p['peak_type'] != 's1': return None
        data = event['processed_waveforms']['top_and_bottom']
        negex = p['lowest_nearby_value'] = min(data[
            max(0,p['left']-500) :
            min(len(data),p['right'] + 101)
        ])  #Window used by s1 filter: todo: don't hardcode    
        maxval =  p['top_and_bottom']['height']
        factor = 3
        if negex<0 and factor * abs(negex) >  maxval:
            return 'Nearby negative excursion of %s, height (%s) not at least %s x as large.' % (negex, maxval, factor)
        return None
        
class PruneS1sInS2Tails(PeakPruner):

    def __init__(self, config):
        PeakPruner.__init__(self, config)

    def decide_peak(self, peak, event, peak_index):
        if peak['peak_type'] != 's1':
            return None
        treshold = 3.12255  # S2 amplitude after which no more s1s are looked for
        if not hasattr(self, 'earliestboundary'):
            s2boundaries = [p['left'] for p in event['peaks'] if is_s2(p) and p['top_and_bottom']['height'] > treshold]
            if s2boundaries == []:
                self.earliestboundary = float('inf')
            else:
                self.earliestboundary = min(s2boundaries)
        if peak['left'] > self.earliestboundary:
            return 'S1 starts at %s, which is beyond %s, the starting position of a "large" S2.' % (peak['left'], self.earliestboundary)
        return None
        
class PruneS2sInS2Tails(PeakPruner):

    def __init__(self, config):
        PeakPruner.__init__(self, config)

    def decide_peak(self, peak, event, peak_index):
        if peak['peak_type'] != 'small_s2':
            return None
        treshold = 624.151  # S2 amplitude after which no more s2s are looked for
        if not hasattr(self, 'earliestboundary'):
            s2boundaries = [p['left'] for p in event['peaks'] if is_s2(p) and p['top_and_bottom']['height'] > treshold]
            if s2boundaries == []:
                self.earliestboundary = float('inf')
            else:
                self.earliestboundary = min(s2boundaries)
        if peak['left'] > self.earliestboundary:
            return 'Small S2 starts at %s, which is beyond %s, the starting position of a "large" S2.' % (peak['left'], self.earliestboundary)
        return None
