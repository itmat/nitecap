import numpy as np


def remove_missing_values(y, sample_collection_times):
    indices_of_finite_values_of_y = np.isfinite(y)
    return (
        y[indices_of_finite_values_of_y],
        sample_collection_times[indices_of_finite_values_of_y],
    )


def enough_timepoints(t, cycle_length):
    return len(set(t % cycle_length)) >= 3


def find_indices_with_enough_timepoints(batch, sample_collection_times, cycle_length):
    indices = []
    for i, y in enumerate(batch):
        _, t = remove_missing_values(y, sample_collection_times)
        if enough_timepoints(t, cycle_length):
            indices.append(i)

    return np.array(indices)
