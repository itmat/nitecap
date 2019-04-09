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

# Number of permutations to take for permuted test statistics
N_PERMS = 2_000
# Number of permutations to compute at one go, reduce this number to reduce memory useage
N_PERMS_PER_RUN = 20

def main(num_replicates_A, data_A, num_replicates_B, data_B):
    """
    Compute the dampening p-values comparing A to B

    `num_replicates_A` is a list of integers indicating how many replicates there are from each timepoint in dataset A
    `data_A` is a numpy array of shape (num_features, num_samples) where num_samples = sum(num_replicates_A)
            containing the values of the condition A
    `num_replicates_B` is a list of integers indicating how many replicates there are from each timepoint in dataset B
    `data_B` is a numpy array of shape (num_features, num_samples) where num_samples = sum(num_replicates_B)
            containing the values of the condition B

    Returns a array of p-values of size (num_features).
    """

    assert data_A.shape[0] == data_B.shape[0]
    N_FEATURES = data_A.shape[0]

    stat = upside_statistic(num_replicates_A, data_A)
    
    num_perms_done = 0
    perm_stat = numpy.empty((N_PERMS, N_FEATURES))
    while True:
        if num_perms_done >= N_PERMS:
            break

        num_perms = min(N_PERMS - num_perms_done, N_PERMS_PER_RUN)
        perm_data = permute(num_replicates_A, data_A, num_replicates_B, data_B, N = num_perms)

        perm_stat[num_perms_done:num_perms_done+num_perms] = upside_statistic(num_replicates_A, perm_data)

        num_perms_done += num_perms

    
    # p-values of the (non-permuted) data
    ps = (numpy.sum(perm_stat >= stat, axis=0) + 1)/ (perm_stat.shape[0]+1)

    return ps

def permute(num_reps_A, data_A, num_reps_B, data_B, N = 1):
    """
    Given data of conditions A and B, return permutations scrambling data of A and B together

    `N` is the number of permutations to create
    Return value is of shape (N, shape of data_A)
    """

    num_reps_A = numpy.array(num_reps_A)
    num_reps_B = numpy.array(num_reps_B)

    # Make slices containing indicating the replicates that occur at each possible time
    time_starts_A = numpy.cumsum(num_reps_A) - num_reps_A[0]
    times_A = [slice(time_start, time_start + reps) for time_start, reps in zip(time_starts_A, num_reps_A)]
    time_starts_B = numpy.cumsum(num_reps_B) - num_reps_B[0]
    times_B = [slice(time_start, time_start + reps) for time_start, reps in zip(time_starts_B, num_reps_B)]

    # First, join the two datasets so that their timepoints are adjacent
    # i.e the collumns will now go T1A T1B T2A T2B T3A T3B...
    data_pieces =  [numpy.concatenate([data_A[:,time_A], data_B[:,time_B]], axis=1)
                                            for (time_A, time_B) in zip(times_A, times_B)]
    data_combined = numpy.concatenate(data_pieces, axis=1).T

    time_starts_combined = numpy.cumsum(num_reps_A + num_reps_B) - (num_reps_A[0] + num_reps_B[0])
    times_combined = [slice(time_start, time_start + reps) for time_start, reps in zip(time_starts_combined, num_reps_A + num_reps_B)]

    # Expand data_combined out to the right number of permutations
    perm_data_combined = numpy.broadcast_to(data_combined, (N,*data_combined.shape)).copy()

    # now shuffle all N copies, shuffling within each timepoint
    # (note numpy.random.shuffle acts in-place so we ignore the generated array)
    [numpy.random.shuffle(perm_data_combined[i,time_slice])
            for time_slice in times_combined
            for i in range(N)]

    # now pull out just the first parts so that we have the un-combined data
    perm_data = numpy.concatenate([perm_data_combined[:, time_start:time_start+A_reps]
                                        for (time_start, A_reps) in zip(time_starts_combined, num_reps_A)],
                                   axis=1)

    return perm_data.swapaxes(1,2)

def upside_statistic(num_reps, data):
    """
    Average within timepoints and then compute the sum of absolute differences between adjacent timepoints

    Data is either 2dim of shape (num_features, num_samples) or
    data is 3 dim of shape (num_perms, num_features, num_samples)
    Returned array is either of shape (num_features) or (num_perms, num_features)
    """

    converted_to_3dim = False
    if data.ndim == 2:
        # Convert to 3-dim if necessary, by making it a single 'permutation'
        converted_to_3dim = True
        data = data.reshape(1,*data.shape)

    # Compute the slices where the times occur
    time_starts = numpy.cumsum(num_reps)  - num_reps[0]
    times = [ slice(0,time_starts[0])] + [slice(time_starts[i], time_starts[i+1])
                                                for i in range(len(time_starts)-1)]
    
    # Average all replicates within each time
    averages = numpy.array([numpy.sum(data[:,:,time_slice],axis=2)/(num_rep)
                                    for (time_slice, num_rep) in zip(times, num_reps)])

    # Sum of absolute differences of adjacent timepoints
    abs_diffs = numpy.abs(averages[1:] - averages[:-1])
    sum_abs_diffs = numpy.sum(abs_diffs, axis=0)  + numpy.abs(averages[0] - averages[-1])

    if converted_to_3dim:
        # If given 2d array, output 1d array
        sum_abs_diffs.shape = sum_abs_diffs.shape[1:]

    return sum_abs_diffs