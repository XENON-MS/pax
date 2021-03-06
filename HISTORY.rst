.. :changelog:

History
-------


------------------
4.9.3 (2016-05-12)
------------------

* Temporarily downgrade scipy due to issues with latest build on some systems
* Event builder: split collections handling, save-all-pulses / mega event / timed trigger mode
* Lowered threshold in XENON1T-LED config until we can specify optimal threshold (#357)
* Waveform simulator bugfix (#354), LED signal simulation (#355)


------------------
4.9.2 (2016-05-03)
------------------

* Poisson likelihood statistic for position reconstruction, confidence contour improvement (#342)
* Event builder: parallel queries, delete-as-we-go, optimized queries, better config / run_doc handling
* Lock-based race condition prevention for ROOT class compilation (see #351)
* Fix wrong numbers in connector map (#349)

------------------
4.9.1 (2016-04-25)
------------------

* Neural net uses correct QEs
* Small changes for event builder
* Split S2 afterpulse models so independent for XENON100 and XENON1T

------------------
4.9.0 (2016-04-18)
------------------

* XENON1T: gains to 1 in LED mode, amplifiers and positions in pmts config dictionary (#339)
* XENON100 S2(x,y) map, XENON100 S2 simulation bugfix (#334)
* Event builder fixes, cax integration
* Pax version no longer append to output filename (0f26ac0)
* Multiprocessing and ROOT fix (#337)
* Waveform simulator afterpulses fix (#341)


------------------
4.8.0 (2016-03-29)
------------------

* New event builder version (#336)

------------------
4.7.0 (2016-03-21)
------------------

* Geant4 input to waveform simulator
* Tuning classification for XENON1T gas-mode zero-field.

------------------
4.6.1 (2016-03-07)
------------------

* Screwed up release, fixing...

------------------
4.6.0 (2016-03-07)
------------------

* Confidence levels on position reconstruction
* Saturation correction bug
* Several small bug fixes
* Minor event builder changes

------------------
4.5.0 (2016-02-26)
------------------

* .cpp classes now included within the ROOT output file (#323)
* Area corrections stored separately in datastructure (#322)
* Waveform simulator refactor, PMT afterpulses support (#321)
* Small event builder changes (#316, several loose commits)

------------------
4.4.1 (2016-02-05)
------------------

* Weird outlier bug fixes found in bulk processing

------------------
4.4.0 (2016-02-02)
------------------

* New event builder iteration (#297)
* Configuration bugs fixed

------------------
4.3.2 (2016-01-31)
------------------

* Small argument fixes for default configuration.

------------------
4.3.1 (2016-01-28)
------------------

* Nasty multiprocessing bug fix

------------------
4.3.0 (2016-01-25)
------------------

* Parallelization refactor (#298)
* Store meta data in ROOT output (#303)
* z coordinate system now negative in liquid (#302)
* Neural net reconstruction (#296)

------------------
4.2.0 (2016-01-11)
------------------

* Fixes for ROOT output: memory leak (#282), LED output (#283), long int fields (#289)
* Event builder changes (#278)
* 3D position reconstruction for S1s (#277)
* Hits and Pulses for S1s saved by default (#283)
* Raw data filename format changed, progress bar fix (#289)

------------------
4.1.2 (2015-11-30)
------------------

* Docs fixes
* TableWriter bug
* Saturation bug #274

------------------
4.1.0 (2015-11-17)
------------------

* ROOT class output
* Signal processing speedup (#245)
* S1 3d pattern simulation & goodness of fit computation (#237)
* Modifications for working with other TPCs (#247)
* Improvements to / fixes for noisy channel hit rejection
* Assorted bug fixes (#241, #244) and documentation fixes

------------------
4.0.1 (2015-10-17)
------------------

* Memory leak fixed
* Corrections to position reconstruction (#244)
* Documentation fixes

------------------
4.0.0 (2015-10-02)
------------------

* Add/remove several peak properties (#223, #214, #203), such as the peak's hits-only sum waveform.
* Clustering changes: separate plugins, better goodness of split, faster (#223, #213)
* Python 2 support (#217)
* Paxer options to switch input and output type (#212)
* Position reconstruction before classification (#223)
* Fast PatternFitter for position reconstruction (#233)
* Irregular correction map support, XENON100 S1(x,y,z) correction (#219)
* S1 vs S2 classification fix (#221)
* Several bugfixes and documentation improvements (e.g. #230)


------------------
3.3.0 (2015-08-03)
------------------

* Natural break declustering (#187)
* Improvements to chi2gamma accuracy and speed (#193, #196)
* Non-continuous events in ZippedBSON format (#192)
* XED writing (#177)
* Refactor plugin base and timing code (#190)
* S2 LCE in waveform simulator (#185)
* Cleanup plugin folders and names (#202)
* Minor improvements to logging (#155, #86) and plotting (#98, #144, #200)
* Documentation improvements


------------------
3.2.0 (2015-07-06)
------------------

* Multithreading of paxer (see --help)
* Clustering bug fixed (#186)
* Contribution section for non-XENON TPCs in examples.
* Chi2 algorithm now runs by default (and has energy cutoff for speed)
* Event builder pretrigger merged into pax
* Units now statically defined
* Various docs improvements


------------------
3.1.2 (2015-06-07)
------------------

* Update requirements.txt

  * Require new numba version since use new features
  * Pymongo3 required for all our Mongo setups

------------------
3.1.1 (2015-06-07)
------------------

* Fixed merge issue with minor release (mea culpa)

------------------
3.1.0 (2015-06-07)
------------------

* Simplified hit finder (#167)
* ZLE in waveform simulator
* BSON output
* Cleanup of Travis building
* Various bug fixes

------------------
3.0.0 (2015-04-20)
------------------

* Reprocessing capability, switch HDF5 backend (#116)
* Better clustering algorithms: MeanShift, GapSize (#124)
* Hitfinder: faster, new noise definition, work on raw ADC data (#126)
* Bad channel rejection -> suspicious channel testing (#126)
* ROOT output, including tests for Travis (#127)
* Speed and feature improvements to folder-based IO (XED, Avro, ...) (#131)
* Datastructure update (#139)
* Bugfixes, plotting and comment improvements

------------------
2.1.0 (2015-02-15)
------------------

 * Avro raw data output
 * Neural net reconstruction
 * And lots of meaningless commits to get Travis continuous integration and Coveralls code coverage to work!  (And ROOT, which will be in 2.2)

------------------
2.0.1 (2015-01-26)
------------------

 * Travis CI continuous integration is enabled
 * Minor bug fixes

   * Values missing from output if they were always default
   * Memory leak after many events due to logger


------------------
2.0.0 (2015-01-15)
------------------

 * Changes to core
 
   * Cleanup of datastructure (see #80 and #81)
   * Most of core wrapped in Processor class
   * Plugins shut down at end of Processor.run(), not just on destruction

 * New signal processing chain

   * BaselineExcursionMethod, finds single-photon peaks in each channel (Default)
   * FindBigPeaks, a traditional sum-waveform peakfinder
   * Supporting peak classification and property computation plugins

 * Chi-square gamma x,y position reconstruction
 * Waveform simulator enhancements

   * Wrapped in Simulator class, loaded along with processor
   * Performance improvements
   * Basic zero-length encoding emulation 
   
 * WritePandas: write our data as DataFrames to containers supported by pandas
 * 2D channel waveforms plot
 * Support for arbitrary external detectors / extra channel groups
 * More tests

 
------------------
1.4.0 (2014-11-21)
------------------

 * DSP
   
   * Peak width fields added to datastructure
   * newDSP: Interpolated peak width computations
   * DSP plugins cleaned up and reorganized (except old peak finder) 
   * Frequency bandpass filtering support
 
 * Updated docs, comments, logging
 * Plots
   
   * 3D channel waveforms plot
   * Event summary plot
 
 * Music output (fun side project)
 * Separate directory for example data files
 * Configurations for XAMS, Bern test setup
 * --input and --output override settings for most plugins
 * WaveformSimulator: improved defaults
 * Stable DAQ injector
 * Various bug fixes and cleanups that polish


------------------
1.3.0 (2014-10-17)
------------------

* Plugin directory moved (fix bug in previous release)
* Bulk processing enhancements

  * Scripts for parallelization
  * XED: read in entire datasets, not just single files

* More command line arguments: input, plotting
* Configuration enhancements

  * Module-level settings
  * Multiple inheritance

* DAQInjector

  * New run-database format
  * Repeat single events
  * Create shard index
  * Further debugging and maturing
  
* Implement run database interface
* WaveformSimulator (Fax) cleanup:

  * Several truth file & instruction file formats
  * Better-motivated settings
  * ER/NR S1s
  
* Cut overhanging pulses
* Several PosSimple improvements 
* Interpolating detector maps (for position-dependent signal corrections)
* Plot 2D hit patterns


------------------
1.2.0 (2014-10-02)
------------------

* DAQ injector - can inject data into DAQs.
* Nested configurations - better handling of configurations and allows for nesting


------------------
1.1.0 (2014-08-29)
------------------

* HDF5 output - will be, for now, default output format.

  * We now have a binary output format for peaks and event.
  * Should also be easily extendible to ROOT output, which is blocked until ROOT solves some Py3.4 bugs.
  * Allows bulk comparison with high statistics for things like trigger efficiency

* Bug fixes relating to difference between XENON100 and XENON1T formats (occurences extending past event windows).
* Starting work on a new SimpleDSP processor
* Waveform generator
* General bug fixes and cleanup

------------------
1.0.0 (2014-08-16)
------------------

* Completely refactored event datastructure

 * Moved from Python dictionaries to an event class, seen in pax.datastructure
 * Ported all modules with pax to the new structure
 * Should open up I/O and C++ binding opportunities
 * Now there are Event, Peak, Waveform, and ReconstructedPosition classes
 * All of this is based on an extensively modified fork of 'micromodels'.

* Input control (See Issue #26)

 * Can now run pax with single events
 * Run paxit --help to see how one can process events

* Binaries of paxit installed when pax is installed
* Improved testing

 * Started testing plugins (this will start including other plugins later in the release)
 * Extensively testing the event class

* Peak finder now nearly identical to Xerawdp: better than 99.9% agreement on >20000 peaks tested

 * Simulation of the Xerawdp convolution bug (filtered waveform mutilation around pulse edges)
 * Small bugfixes (empty isolation test regions, strange behaviour when max of filtered waveform is negative)
 * Xerawdp XML file interpretation is off-by one (min_width=10 means: width must be 11 or higher)

* Integration of a waveform simulator (FaX) which can simulate S1s, S2s, and white noise

 * Script to convert from MC/NEST root files to FaX instructions
 * Simplified but much faster simulation mode used for peaks >1000 pe

* Plotting improvement: largest S1 & S2 in separate subplot
* Numerous bug fixes:

 * Pickler I/O
 * Remove dead code (clustering)




------------------
0.2.1 (2014-08-14)
------------------

* paxit binaries installed by default to allow working out of source

------------------
0.2.0 (2014-08-04)
------------------

* Define static event class data structure
* Transforms now specified in ini file
* Can launch small web server for viewing plots
* Major changes to the peak finding to better match Xerawdp. Agreement is currently at the 95% level.

 * Two important bugfixes for determining included channels : XED channel mask parsing, 0->1 start
 * Filter impulse response now identical to Xerawdp
 * Different summed waveforms for s1 and s2 peakfinding

* Transforms have start and stop methods

------------------
0.1.0 (2014-07-18)
------------------

* First release of software framework
* Functional but not complete digital signal processing
  * Sum waveform for top, bottom, veto
  * Filtering with raised cosine filter
  * Peak finding of S1 and S2
* Basic inputs
  * MongoDB (used online for DAQ)
  * XED (XENON100 format)
* Basic outputs
  * ROOT
  * Pickle
  * Plots
* Demo reconstruction algorithm of charge-weighted sum
