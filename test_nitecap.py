'''
Runs nitecap on several specific profiles so that we can consistently assess Nitecap's performance on these
'''
import numpy
numpy.random.seed(1)

import nitecap

traces = [
    # Completely Flat
    [0, 0, 0, 0, 0, 0],
    # A nice curve, should be great
    [0, 0.3, 1.0, -0.3,-1.0, -0.5],
    # Flat then spike
    [-1, -1, 1, -1, -1, -1],
    # Flat then double-wide spike
    [-1, 1, 1, -1, -1, -1],
    # Flat then triple-wide spike (ie half up half down)
    [1, 1, 1, -1, -1, -1],
    # Flat with two spikes
    [-1, 1, -1, 1, -1, -1],
    # Very ragged
    [1, -1, 0.3, -0.9, 0.8, 0.2],
    # Smooth spike
    [-1, -0.3, 1, -0.3, -1, -1],
    # Smoother spike
    [-1, 0, 1, 0, -1, -1],
    ]

# Each trace above gets copied this many times and has noise added to it
N_COPIES = 20
NOISE = 0.6
N_TIMEPOINTS = 6
N_REPS = 1
N_CYCLES = 1

data = numpy.concatenate([numpy.repeat(trace, N_COPIES).reshape((-1,N_COPIES)).T for trace in traces])
data += NOISE * numpy.random.random(data.shape)

# Run nitecap
q, td, perm_td  = nitecap.main(data, N_TIMEPOINTS, N_REPS, N_CYCLES, output="full")
rank = numpy.empty(shape=td.shape)
rank[numpy.argsort(td)] = numpy.arange(len(td))
p = (numpy.sum(perm_td <= td, axis=0) + 1)/ (perm_td.shape[0]+1)

# Aggregate the values by which trace they occur for
td_by_trace = numpy.array([td[i*N_COPIES:(i+1)*N_COPIES] for i in range(len(traces))])
p_by_trace = numpy.array([p[i*N_COPIES:(i+1)*N_COPIES] for i in range(len(traces))])
q_by_trace = numpy.array([q[i*N_COPIES:(i+1)*N_COPIES] for i in range(len(traces))])
rank_by_trace = numpy.array([rank[i*N_COPIES:(i+1)*N_COPIES] for i in range(len(traces))])

avg_td_by_trace = numpy.mean(td_by_trace, axis=1)
avg_p_by_trace = numpy.mean(p_by_trace, axis=1)
std_td_by_trace = numpy.std(td_by_trace, axis=1)
avg_q_by_trace = numpy.mean(q_by_trace, axis=1)
avg_rank_by_trace = numpy.mean(rank_by_trace, axis=1)
