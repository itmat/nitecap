import numpy

import nitecap

TARGET_FDR = 0.1

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
N_GENES = 200
PORTION_CIRC = 0.2 # Fraction of genes that are 'circadian'
MAX_AMPLITUDE  = 0.3

N_CIRC = int(N_GENES * PORTION_CIRC)
N_NONCIRC = N_GENES - N_CIRC

# Read depths with average of 400 and large variation, many smallish
AVG_DEPTHS = numpy.random.gamma(4, 100, size=(1,1,N_GENES))

# Amplitudes of oscillation
AMPLITUDES = numpy.array( [0]*N_NONCIRC #The non-circ parts
            + [numpy.random.random()*MAX_AMPLITUDE for i in range(N_CIRC)] ) # The circ parts
AMPLITUDES.shape = (1,1,N_GENES)

DATA_MEANS = (WAVEFORM * AMPLITUDES * AVG_DEPTHS) + AVG_DEPTHS


###### Create the random data
data = numpy.random.poisson(DATA_MEANS, size=(N_TIMEPOINTS, N_REPS, N_GENES))
data = data.reshape( (N_TIMEPOINTS * N_REPS, N_GENES) ).swapaxes(0,1)#Group all replicates in a timepoint

##### Run nitecap
# Use the following for most use-cases:
#q, td, perm_td  = nitecap.nitecap(data, N_TIMEPOINTS, N_REPS, N_CYCLES)

# We use this instead for plotting results
q, td, perm_td  = nitecap.nitecap(data, N_TIMEPOINTS, N_REPS, N_CYCLES, output="full")


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
CUTOFF = numpy.sort(td)[num_rejected]
print(f"Rejected {num_rejected} genes with FDR <= {TARGET_FDR}")
print(f"True proportion of false discoveries was {num_false_positives / num_rejected:.2f} with {num_false_positives} false rejections")
print(f"Found {num_rejected - num_false_positives} true positives out of a total of {N_CIRC} possible")

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
