import numpy as np

from algorithms.upside.upside import main
from itertools import islice

BATCH_SIZE = 200

def upside(data, sample_collection_times, cycle_length=24):
    
    groups = []
    
    for collection_times in sample_collection_times:
        timepoints = sorted(set(collection_times))
        Δt = float(timepoints[1] - timepoints[0])

        groups.append(np.round((collection_times % cycle_length) / Δt).astype(int))

    p = []
    while batch := list(islice(data, BATCH_SIZE)):
        data_A, data_B = zip(*batch)

        p.extend(
            main(
                groups[0], np.array(data_A),
                groups[1], np.array(data_B),
                timepoints_per_cycle=round(cycle_length / Δt),
            )
        )

    return [p]
