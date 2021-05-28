"""
Conversion of the 'upside' dampening analysis from Perl to Python for Nitecap

Compares two conditions, say A versus B, over a timeseries by computing, first for samples in condition A,
the average at each timepoint and then the sum of the absolute differences between adjacent timepoints' averages.
This is compared to the same sum computed over permutations where replicates from conditions A and B are scrambled
while preserving the timepoint that they occur at.
Permutation p-values are then computed by counting the number of permutations of replciates which give a lower
absolute sum of differences.

A gene is said to 'dampen' from condition A to condition B if this p-value is small.
"""

import numpy

from . import util

# Number of permutations to take for permuted test statistics
N_PERMS = 2_000
# Number of permutations to compute at one go, reduce this number to reduce memory useage
N_PERMS_PER_RUN = 20

def main(timepoints_A, data_A, timepoints_B, data_B, timepoints_per_cycle, repeated_measures=False):
    """
    Compute the dampening p-values comparing A to B

    `timepoints_A` is a list of integers indicating timepoint of each column of data_A
    `data_A` is a numpy array of shape (num_features, num_samples)
            containing the values of the condition A
    `timepoints_B` is a list of integers indicating timepoint of each column of data_B
    `data_B` is a numpy array of shape (num_features, num_samples)
            containing the values of the condition B
    `timepoints_per_cycle` is the number of timepoints per complete cycle
    `repeated_measures` is whether the data was taken from individuals repeatedly. Leave as False if
            each datapoint is independent. If True, must position the individuals consistently,
            e.g. first individual always is first in each timepoint in its dataset

    Returns a array of p-values of size (num_features).
    """

    assert data_A.shape[0] == data_B.shape[0]
    assert data_A.shape[1] == len(timepoints_A)
    assert data_B.shape[1] == len(timepoints_B)

    data_A = data_A.astype(float)
    data_B = data_B.astype(float)

    # First thing we do is to normalize the medians of the two datasets A and B
    # otherwise a constant offset between the two makes a dramatic difference
    A_median = numpy.nanmedian(data_A, axis=1)
    B_median = numpy.nanmedian(data_B, axis=1)
    data_B += (A_median - B_median)[:, None]

    N_FEATURES = data_A.shape[0]

    stat = upside_statistic(data_A, timepoints_A, timepoints_per_cycle, repeated_measures=repeated_measures)
    
    num_perms_done = 0
    perm_stat = numpy.empty((N_PERMS, N_FEATURES))
    while True:
        if num_perms_done >= N_PERMS:
            break

        num_perms = min(N_PERMS - num_perms_done, N_PERMS_PER_RUN)
        perm_data = permute(timepoints_A, data_A, timepoints_B, data_B, timepoints_per_cycle, N = num_perms, repeated_measures=repeated_measures)

        perm_stat[num_perms_done:num_perms_done+num_perms] = upside_statistic(perm_data, timepoints_A, timepoints_per_cycle, repeated_measures=repeated_measures)

        num_perms_done += num_perms

    # p-values of the (non-permuted) data
    ps = (numpy.sum(perm_stat >= stat, axis=0) + 1)/ (perm_stat.shape[0]+1)

    return ps

def permute(timepoints_A, data_A, timepoints_B, data_B, timepoints_per_cycle, N = 1, repeated_measures=False):
    """
    Given data of conditions A and B, return permutations scrambling data of A and B together
    If `repeated_measures` then keep corresponding datapoints together as if from same sample.
        I.e. the first datapoint of each timepoint is from Individual 1, then we better not scramble
        those across individuals

    `N` is the number of permutations to create
    Return value is of shape (N, shape of data_A)
    """

    N_SAMPLES_A = data_A.shape[1]
    N_SAMPLES_b = data_B.shape[1]

    # Make slices indicating the replicates that occur at each possible time
    indexes_for_timepoint_A = [[i for i,t in enumerate(timepoints_A) if (t % timepoints_per_cycle) == j]
                                for j in range(timepoints_per_cycle)]
    # for B, we offset so that there's space for A's samples too
    indexes_for_timepoint_B = [[i+N_SAMPLES_A for i,t in enumerate(timepoints_B) if (t % timepoints_per_cycle) == j]
                                for j in range(timepoints_per_cycle)]
    # Indexes by timepoints for joined datasets of both A and B
    joined_indexes = [indexes_A + indexes_B for indexes_A, indexes_B in zip(indexes_for_timepoint_A, indexes_for_timepoint_B)]

    num_reps_A = [len(indexes) for indexes in indexes_for_timepoint_A]

    #time_starts_A = numpy.cumsum(num_reps_A) - num_reps_A[0]
    #times_A = [slice(time_start, time_start + reps) for time_start, reps in zip(time_starts_A, num_reps_A)]
    #time_starts_B = numpy.cumsum(num_reps_B) - num_reps_B[0]
    #times_B = [slice(time_start, time_start + reps) for time_start, reps in zip(time_starts_B, num_reps_B)]

    # First, join the two datasets so we can index both
    data_joined = numpy.concatenate((data_A, data_B), axis=1)

    # Expand data_combined out to the right number of permutations
    #perm_data_combined = numpy.broadcast_to(data_combined, (N,*data_combined.shape)).copy()

    if not repeated_measures:
        permuted_data = [numpy.concatenate([data_joined[:, numpy.random.choice(indexes, reps, replace=False)]
                                            for indexes, reps in zip(joined_indexes, num_reps_A)], axis=1)
                                for i in range(N)]
        permuted_data = numpy.array(permuted_data)
    else:
        raise NotImplementedError
        # We haven't reworked this and don't really support repeated measures anyway
        num_A_replicates = times_A[0].stop - times_A[0].start
        num_B_replicates = times_B[0].stop - times_B[0].start
        for i in range(N):
            shuffled_replicates = numpy.random.permutation(num_A_replicates + num_B_replicates)
            for time_slice in times_combined:
                perm_data_combined[i,time_slice] = perm_data_combined[i,time_slice][shuffled_replicates]

    return permuted_data

def upside_statistic(data, timepoints, timepoints_per_cycle, repeated_measures=False):
    """
    Average within timepoints and then compute the sum of absolute differences between adjacent timepoints

    Data is 2dim of shape (num_features, num_samples) or 3d of shape (num_perms, num_features, num_samples)
    timepoints is of shape (num_samples)
    timepoints_per_cycle is the number of timepoints in a complete cycle
    repeated_measures is whether the data was taken from the same subjects repeatedly, or False if all independent
    Returned array is either of shape (num_features) or (num_perms, num_features)
    """

    converted_to_3dim = False
    if data.ndim == 2:
        # Convert to 2-dim if necessary, by making it a single 'permutation'
        converted_to_3dim = True
        data = data.reshape((1,*data.shape))

    N_PERMS, N_FEATURES, N_SAMPLES = data.shape

    indexes_for_timepoint = [[i for i,t in enumerate(timepoints) if (t % timepoints_per_cycle) == j]
                                for j in range(timepoints_per_cycle)]

    # Average all replicates within each time
    averages = numpy.array([numpy.nanmean(data[:,:,timepoint_slice],axis=2)
                                    for timepoint_slice in indexes_for_timepoint])

    # Sum of absolute differences of adjacent timepoints
    abs_diffs = numpy.abs(averages[1:] - averages[:-1])
    wrap_around_diff = numpy.abs(averages[0] - averages[-1])

    util.zero_nans(abs_diffs)
    util.zero_nans(wrap_around_diff)

    sum_abs_diffs = numpy.sum(abs_diffs, axis=0)   + wrap_around_diff

    if converted_to_3dim:
        # If given 2d array, output 1d array
        sum_abs_diffs.shape = sum_abs_diffs.shape[1:]

    return sum_abs_diffs
