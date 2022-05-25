import numpy as np
import rpy2.robjects as R

from itertools import islice
from pathlib import Path

from rpy2.robjects import numpy2ri
from rpy2.robjects.packages import STAP

from utilities import find_indices_with_enough_timepoints

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
    sample_collection_times_indices = np.round(sample_collection_times / Δt).astype(int)

    measure_sequence = np.zeros(number_of_timepoints)
    for sample_collection_times_index in sample_collection_times_indices:
        measure_sequence[sample_collection_times_index] += 1

    p = []
    while batch := list(islice(data, BATCH_SIZE)):
        y = np.array(batch)

        indices_with_enough_timepoints = find_indices_with_enough_timepoints(
            y, sample_collection_times, cycle_length
        )

        P = np.full(len(y), np.nan)
        P.put(
            indices_with_enough_timepoints,
            RAIN.rain(
                y[indices_with_enough_timepoints].T,
                period=cycle_length,
                deltat=Δt,
                measure_sequence=measure_sequence,
                na_rm=bool(np.isnan(y).any()),
            ).rx2("pVal"),
        )

        p.extend(P)

    return [p]
