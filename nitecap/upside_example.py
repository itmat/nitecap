import time
import numpy

import upside
import util

###### Parameters for generated data
# Always generate the same random data
numpy.random.seed(3)

REPEATED_MEASURES = True

N_TIMEPOINTS = 6 # 6 timepoints total per cycle (ie day)
N_REPS = 8 # 4 replicates per timepoint
N_CYCLES = 1 # One day of data

# Sampling every 4 hours
WAVEFORM = [0, -0.8, -1.0, 0.3, 1.0, 0.60] # A nice, simple wave form
WAVEFORM= 1/2*numpy.array(WAVEFORM)
WAVEFORM.shape = (-1,1,1)
N_GENES = 1000
PORTION_DAMPENED = 0.2 # Fraction of genes that are 'circadian'
MAX_AMPLITUDE  = 0.5

N_DAMPENED = int(N_GENES * PORTION_DAMPENED)
N_NONDAMPENED = N_GENES - N_DAMPENED

# Read depths with average of 400 and large variation, many smallish
AVG_DEPTHS = numpy.random.gamma(4, 100, size=(1,1,N_GENES))

# Amplitudes of oscillation
AMPLITUDES = numpy.random.random(N_GENES)*MAX_AMPLITUDE
AMPLITUDES.shape = (1,1,N_GENES)

DATA_MEANS = (WAVEFORM * AMPLITUDES * AVG_DEPTHS) + AVG_DEPTHS

if REPEATED_MEASURES:
    # Each replicate gets a random additive amount ontop
    DATA_MEANS = DATA_MEANS + DATA_MEANS[0] * numpy.random.uniform(0.0, 0.2, size=(1, N_REPS, N_GENES))

###### Create the random data
data = numpy.random.poisson(DATA_MEANS, size=(N_TIMEPOINTS, N_REPS, N_GENES))
data = data.reshape( (N_TIMEPOINTS * N_REPS, N_GENES) ).swapaxes(0,1)#Group all replicates in a timepoint

# B-condition which is the same as A except that some are dampened (amplitude multiplied by a random number 0 to 0.75)
DAMPENED_AMPLITUDES = AMPLITUDES.copy()
DAMPENED_AMPLITUDES[:,:,:N_DAMPENED] *= numpy.random.random(N_DAMPENED) * 0.75
MEAN_RATIOS =  1#numpy.exp(numpy.random.uniform(-0.3,0.3))
DAMPENED_DATA_MEANS = (WAVEFORM * DAMPENED_AMPLITUDES * AVG_DEPTHS) + AVG_DEPTHS * MEAN_RATIOS
if REPEATED_MEASURES:
    # Each replicate gets a random additive amount ontop
    DAMPENED_DATA_MEANS = DAMPENED_DATA_MEANS + DAMPENED_DATA_MEANS[0] * numpy.random.uniform(0.0, 0.2, size=(1, N_REPS, N_GENES))
data_B = numpy.random.poisson(DAMPENED_DATA_MEANS, size=(N_TIMEPOINTS,  N_REPS, N_GENES))
data_B = data_B.reshape( (N_TIMEPOINTS * N_REPS, N_GENES) ).swapaxes(0,1)#Group all replicates in a timepoint

# timing measurement
start = time.time()

##### Run upside
# We use this instead for plotting results
ps = upside.main([N_REPS]*N_TIMEPOINTS, data,
                 [N_REPS]*N_TIMEPOINTS, data_B,
                 repeated_measures=REPEATED_MEASURES)
##### End upside

# Finish timing
end = time.time()
print(f"Ran upside on {N_GENES} genes in {end-start:.2f} seconds")
print(f"Estimate {numpy.sum(ps)*2:0.1f} nulls out of {N_GENES}")

# FDR computations
qs = util.BH_FDR(ps)

# Compare FDR results to truth
sort_order = numpy.argsort(ps)
is_null = numpy.array([0]*N_DAMPENED + [1]*N_NONDAMPENED)
num_nulls_so_far = numpy.cumsum(is_null[sort_order])
real_qs = num_nulls_so_far / numpy.arange(1,N_GENES+1)


# Plotting
import pylab
pylab.scatter(qs[sort_order], real_qs)
pylab.plot([0,1],[0,1])
pylab.xlabel("Reported FDR")
pylab.ylabel("True FDR")
pylab.show()
