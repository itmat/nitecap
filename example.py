import time
import numpy

import nitecap

TARGET_FDR = 0.1
REPEATED_MEASURES = True

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
PORTION_CIRC = 0.2 # Fraction of genes that are 'circadian'
MAX_AMPLITUDE  = 0.3
TIMEPOINT_NOISE = 0.02 # Small amount of variation of between timepoints, consistent among replicates in that timepoint

N_CIRC = int(N_GENES * PORTION_CIRC)
N_NONCIRC = N_GENES - N_CIRC

# Read depths with average of 400 and large variation, many smallish
AVG_DEPTHS = numpy.random.gamma(4, 100, size=(1,1,N_GENES))

# Amplitudes of oscillation
AMPLITUDES = numpy.array( [0]*N_NONCIRC #The non-circ parts
            + [numpy.random.random()*MAX_AMPLITUDE for i in range(N_CIRC)] ) # The circ parts
AMPLITUDES.shape = (1,1,N_GENES)

DATA_MEANS = (WAVEFORM * AMPLITUDES * AVG_DEPTHS) + AVG_DEPTHS
DATA_MEANS *= numpy.random.uniform(1 - TIMEPOINT_NOISE, 1 + TIMEPOINT_NOISE, size=(N_TIMEPOINTS, 1, N_GENES))

if REPEATED_MEASURES:
    # For repeated measures, each replicate gets a random constant added to its mean
    DATA_MEANS = DATA_MEANS + DATA_MEANS[0] * numpy.random.uniform(0.0, 1.5, size=(1, N_REPS, N_GENES))

###### Create the random data
data = numpy.random.poisson(DATA_MEANS, size=(N_TIMEPOINTS, N_REPS, N_GENES))
data = data.reshape( (N_TIMEPOINTS * N_REPS, N_GENES) ).swapaxes(0,1)#Group all replicates in a timepoint


# timing measurement
start = time.time()

##### Run nitecap
# Use the following for most use-cases:
#q, td = nitecap.main(data, N_TIMEPOINTS, N_REPS, N_CYCLES)

# We use this instead for plotting results
q, td, perm_td  = nitecap.main(data, N_TIMEPOINTS, N_REPS, N_CYCLES,
                                output="full", # For display purposes
                                repeated_measures=REPEATED_MEASURES,)
##### End nitecap

# Finish timing
end = time.time()
print(f"Ran nitecap on {N_GENES} genes in {end-start:.2f} seconds")


####### Compute the actual false discoveries and report the results
sort_order = numpy.argsort(td)
realized_q = numpy.ones(N_GENES)
for gene in sort_order: # Doesn't actually need to be in sorted order
    cutoff = td[gene]
    found, = numpy.where(td <= cutoff)
    num_rejected = len(found)
    num_false_positives = numpy.sum(found < N_NONCIRC)
    realized_q[gene] = num_false_positives/num_rejected

found, = numpy.where(q <= TARGET_FDR)
num_rejected = len(found)
num_false_positives = numpy.sum(found < N_NONCIRC)
if num_rejected > 0:
    CUTOFF = numpy.sort(td)[num_rejected-1]
    print(f"Rejected {num_rejected} genes with FDR <= {TARGET_FDR}")
    print(f"True proportion of false discoveries was {num_false_positives / num_rejected:.2f} with {num_false_positives} false rejections")
    print(f"Found {num_rejected - num_false_positives} true positives out of a total of {N_CIRC} possible")
else:
    print(f"No genes were rejected at FDR <= {TARGET_FDR}")
    CUTOFF = float('-inf')

###### Plot the data
import pylab
fig = pylab.figure()
ax = fig.add_subplot(111)

xs = numpy.arange(N_GENES)
[ax.scatter(xs, perm_td[i], alpha=0.05, color="red", s=1) for i in range(nitecap.N_PERMS)]
ax.scatter(xs, td, s=3, color="black")

ax.hlines( [CUTOFF], xmin = min(xs), xmax = max(xs), linestyle="dashed")

fig2 = pylab.figure()
ax2 = fig2.add_subplot(111)
ax2.scatter(q, realized_q)
ax2.plot([0,1],[0,1], color="black")
ax2.set_xlabel("Estimated FDR")
ax2.set_ylabel("Real FDR")
ax2.set_xlim(0,1)
ax2.set_ylim(0,1)
ax2.hlines( [1-PORTION_CIRC], xmin = 0, xmax = 1)

pylab.show()
