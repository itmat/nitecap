import numpy as np
import rpy2.robjects as R

from itertools import islice
from pathlib import Path

from rpy2.robjects import numpy2ri
from rpy2.robjects.packages import STAP

numpy2ri.activate()

R.r.library("multtest")
R.r.library("gmp")

BATCH_SIZE = 200


def rain(data, sample_collection_times, cycle_length=24):
    with open(Path(__file__).parent / "algorithm.R") as algorithm:
        RAIN = STAP(algorithm.read(), "RAIN")

    timepoints = sorted(set(sample_collection_times))
    Δt = float(timepoints[1] - timepoints[0])

    number_of_timepoints = len(timepoints)
    sample_collection_times_indices = (sample_collection_times / Δt).astype(int)

    measure_sequence = np.zeros(number_of_timepoints)
    for sample_collection_times_index in sample_collection_times_indices:
        measure_sequence[sample_collection_times_index] += 1

    p = []
    while batch := list(islice(data, BATCH_SIZE)):
        y = R.r.matrix(np.array(batch).T, nrow=len(sample_collection_times), ncol=len(batch))
        p.extend(
            RAIN.rain(
                y,
                period=cycle_length,
                deltat=Δt,
                measure_sequence=R.FloatVector(measure_sequence),
                na_rm=True,
            ).pVal
        )

    return [p]
