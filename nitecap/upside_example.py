import time
import numpy

import nitecap.upside

###### Parameters for generated data
# Always generate the same random data
numpy.random.seed(3)

N_TIMEPOINTS = 6 # 6 timepoints total per cycle (ie day)
N_REPS = 4 # 4 replicates per timepoint
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

###### Create the random data
data = numpy.random.poisson(DATA_MEANS, size=(N_TIMEPOINTS, N_REPS, N_GENES))
data = data.reshape( (N_TIMEPOINTS * N_REPS, N_GENES) ).swapaxes(0,1)#Group all replicates in a timepoint

# B-condition which is the same as A except that some are dampened (amplitude multiplied by a random number 0 to 0.75)
DAMPENED_AMPLITUDES = AMPLITUDES.copy()
DAMPENED_AMPLITUDES[:,:,:N_DAMPENED] *= numpy.random.random(N_DAMPENED) * 0.75
DAMPENED_DATA_MEANS = (WAVEFORM * DAMPENED_AMPLITUDES * AVG_DEPTHS) + AVG_DEPTHS
data_B = numpy.random.poisson(DAMPENED_DATA_MEANS, size=(N_TIMEPOINTS,  N_REPS, N_GENES))
data_B = data_B.reshape( (N_TIMEPOINTS * N_REPS, N_GENES) ).swapaxes(0,1)#Group all replicates in a timepoint

# timing measurement
start = time.time()

##### Run upside
# We use this instead for plotting results
ps = nitecap.upside.main([N_REPS]*N_TIMEPOINTS, data,
                         [N_REPS]*N_TIMEPOINTS, data_B)
##### End upside

# Finish timing
end = time.time()
print(f"Ran upside on {N_GENES} genes in {end-start:.2f} seconds")
print(f"Estimate {numpy.sum(ps)*2} nulls out of {N_GENES}")