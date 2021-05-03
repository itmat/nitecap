import time
import numpy

import upside
import util

###### Parameters for generated data
# Always generate the same random data
numpy.random.seed(3)

N_TIMEPOINTS = 6 # 6 timepoints total per cycle (ie day)
N_REPS = 4 # 4 replicates per timepoint
N_CYCLES = 1 # One day of data

N_GENES = 1000

# Sampling every 4 hours
PHASES = numpy.random.uniform(low=0.0, high=2*numpy.pi, size=(1,1,N_GENES))
Ts = (numpy.arange(N_TIMEPOINTS)*2*numpy.pi/N_TIMEPOINTS).reshape((-1,1,1))
WAVEFORM = numpy.cos(Ts + PHASES)/2
PORTION_DAMPENED = 0.2 # Fraction of genes whose amplitude is dampened
PORTION_PHASE_OFFSET = 0.2 # Fraction of genes that are shifted in Phase between the two conditions
MAX_AMPLITUDE  = 0.5
MIN_AMPLITUDE = 0.2

N_DAMPENED = int(N_GENES * PORTION_DAMPENED)
N_NONDAMPENED = N_GENES - N_DAMPENED
N_PHASE_OFFSET = int(N_GENES * PORTION_PHASE_OFFSET)
N_NONPHASE_OFFSET = N_GENES - N_PHASE_OFFSET

# Read depths with average of 400 and large variation, many smallish
AVG_DEPTHS = numpy.random.gamma(4, 100, size=(1,1,N_GENES))

# Amplitudes of oscillation
AMPLITUDES = numpy.random.random(N_GENES)*(MAX_AMPLITUDE - MIN_AMPLITUDE) + MIN_AMPLITUDE
AMPLITUDES.shape = (1,1,N_GENES)

DATA_MEANS = (WAVEFORM * AMPLITUDES * AVG_DEPTHS) + AVG_DEPTHS

###### Create the random data
data = numpy.random.poisson(DATA_MEANS, size=(N_TIMEPOINTS, N_REPS, N_GENES))
data = data.reshape( (N_TIMEPOINTS * N_REPS, N_GENES) ).swapaxes(0,1)#Group all replicates in a timepoint

# B-condition which is the same as A except that some are dampened (amplitude multiplied by a random number 0 to 0.75)
DAMPENED_AMPLITUDES = AMPLITUDES.copy()
DAMPENED_AMPLITUDES[:,:,:N_DAMPENED] *= numpy.random.random(N_DAMPENED) * 0.75

OFFSET_PHASES = PHASES.copy() # Randomly offset phases by an amount in (0,pi)
OFFSET_PHASES[:,:,N_DAMPENED:N_DAMPENED+N_PHASE_OFFSET] += numpy.random.random(N_DAMPENED) * numpy.pi
WAVEFORM_B = numpy.cos(Ts + OFFSET_PHASES)/2

DAMPENED_DATA_MEANS = (WAVEFORM_B * DAMPENED_AMPLITUDES * AVG_DEPTHS) + AVG_DEPTHS
data_B = numpy.random.poisson(DAMPENED_DATA_MEANS, size=(N_TIMEPOINTS,  N_REPS, N_GENES))
data_B = data_B.reshape( (N_TIMEPOINTS * N_REPS, N_GENES) ).swapaxes(0,1)#Group all replicates in a timepoint

# timing measurement
start = time.time()

##### Run upside
# We use this instead for plotting results
upside_ps = upside.main([N_REPS]*N_TIMEPOINTS, data,
                         [N_REPS]*N_TIMEPOINTS, data_B)
##### End upside

# Finish timing
end = time.time()
print(f"Ran upside on {N_GENES} genes in {end-start:.2f} seconds")
print(f"Estimate {numpy.sum(upside_ps)*2} nulls out of {N_GENES}")

### RUN cosinor analysis
start = time.time()
amplitude_ps, phase_ps = util.cosinor_analysis([N_REPS]*N_TIMEPOINTS, data,
                                               [N_REPS]*N_TIMEPOINTS, data_B)
end = time.time()
###
print(f"Ran Cosinor analysis on {N_GENES} genes in {end-start:.2f} seconds")

# FDR computations
upside_qs = util.BH_FDR(upside_ps)
amplitude_qs = util.BH_FDR(amplitude_ps)
phase_qs = util.BH_FDR(phase_ps)

# Compare FDR results to truth
sort_order = numpy.argsort(upside_ps)
is_null = numpy.array([0]*N_DAMPENED + [1]*N_NONDAMPENED)
num_nulls_so_far = numpy.cumsum(is_null[sort_order])
real_qs = num_nulls_so_far / numpy.arange(1,N_GENES+1)

# Plotting
import pylab
pylab.scatter(upside_qs[sort_order], real_qs)
pylab.plot([0,1],[0,1])
pylab.xlabel("Reported FDR")
pylab.ylabel("True FDR")
pylab.show()
