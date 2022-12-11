import numpy as np

from algorithms.upside.upside import main
from itertools import chain, islice, permutations

BATCH_SIZE = 200


def upside(data, sample_collection_times, cycle_length=24):

    groups = []

    for collection_times in sample_collection_times:
        timepoints = sorted(set(collection_times))
        Δt = float(timepoints[1] - timepoints[0])

        groups.append(np.round((collection_times % cycle_length) / Δt).astype(int))

    p = [[], []]

    while batch := list(islice(data, BATCH_SIZE)):
        for i, groups_and_data in enumerate(
            permutations(zip(groups, map(np.array, zip(*batch))))
        ):
            p[i].extend(
                main(
                    *chain(*groups_and_data),
                    timepoints_per_cycle=round(cycle_length / Δt),
                )
            )

    return p


if __name__ == "__main__":
    a = [(np.array([1, 2, 3, 4, 5, 6]), np.array([4, 2, 1, 31, 12, 2]))] * 10

    sample_collection_times = [
        np.array([0.0, 6.0, 12.0, 18.0, 24.0, 30.0]),
        np.array([0.0, 6.0, 12.0, 18.0, 24.0, 30.0]),
    ]

    print(upside((x for x in a), sample_collection_times))
