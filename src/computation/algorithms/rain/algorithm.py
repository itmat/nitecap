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


def rain(data, timepoints):
    with open(Path(__file__).parent / "algorithm.R") as algorithm:
        RAIN = STAP(algorithm.read(), "RAIN")

    t_0, t_1, *_ = sorted(set(timepoints))
    Δt = float(t_1 - t_0)

    number_of_timepoints = len(set(timepoints))
    timepoints_indices = (timepoints / Δt).astype(int)

    measure_sequence = np.zeros(number_of_timepoints)
    for timepoint_index in timepoints_indices:
        measure_sequence[timepoint_index] += 1

    p = []
    while batch := list(islice(data, BATCH_SIZE)):
        y = R.r.matrix(np.array(batch).T, nrow=timepoints.size, ncol=len(batch))
        p.extend(
            RAIN.rain(
                y,
                period=24,
                deltat=Δt,
                measure_sequence=R.FloatVector(measure_sequence),
                na_rm=True,
            ).pVal
        )

    return [p]
