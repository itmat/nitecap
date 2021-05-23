# cython: language_level=3
import cython
import numpy

@cython.cdivision(True) # Use c-style % operator (always have positive values)
def sum_abs_differences(data_in, timepoints, timepoint_permutations, int timepoints_per_cycle, data_out):
    '''
    NOw takes timepoint_permutations of shape (N_PERMUTATIONS, NUM_TIMEPOINTS)
    '''
    ''' takes in numpy array of data_in of shape (N_FEATURES, N_SAMPLES) and timpepoints of shape (N_SAMPLES) mapping each column of data_in to the its corresponding timepoint
    Writes out to data_out of shape (N_PERMUTATIONS, N_FEATURES) the sum of the absolute differences of each
    sample from all the samples in adjacent timepoints for each feature and timepoint permutations
    '''
    # Enforce the necessary array shapes
    assert len(data_in.shape) == 2, "data_in should have 2 dimensions"
    assert len(timepoints.shape) == 1, "timepoints should have 1 dimensions"
    assert len(timepoint_permutations.shape) == 2, "timepoint_permutations should have 2 dimensions"
    assert len(data_out.shape) == 2, "data_out should have 2 dimensions"
    assert data_in.shape[0] == data_out.shape[1], "data_in and data_out need to match size"
    assert data_in.shape[1] == timepoints.shape[0], "data_in and timepoints need to match in size"
    assert timepoint_permutations.shape[0] == data_out.shape[0], "data_out and timepoint_permutations need to match in size"
    #assert data_in.dtype == float, "data_in must by float type"
    #assert data_out.dtype == float, "data_out must be float type"
    #assert timepoints.dtype == int, "timepoints must be integer type"
    assert timepoints.min() >= 0, "timepoints cannot have values less than 0"
    assert timepoints.max() < timepoint_permutations.shape[1], "timepoints cannot have values larger than timepoint_permutations second dimension"
    assert timepoint_permutations.min() >= 0, "timepoint permutations cannot have values less than 0"
    assert timepoint_permutations.max() == timepoints_per_cycle-1, "timepoint_permutations contain values 0 to timepoints_per_cycle-1"

    cdef Py_ssize_t num_features = data_in.shape[0]
    cdef Py_ssize_t num_samples = data_in.shape[1]
    cdef Py_ssize_t num_permutations = timepoint_permutations.shape[0]
    cdef Py_ssize_t num_timepoints = timepoints.max() + 1

    # cdef the indexes/iterators we use later so type is known
    cdef Py_ssize_t timepoint, next_timepoint, feature
    cdef Py_ssize_t rep1, rep2
    cdef Py_ssize_t idx1, idx2
    cdef Py_ssize_t timepoint1, timepoint2

    # Make views of the numpy array
    cdef double[:, :] data_view = data_in
    cdef double[:, :] out_view = data_out
    cdef int[:] timepoints_view = timepoints
    cdef int[:,:] timepoint_permutations_view = timepoint_permutations

    cdef double total = 0;
    cdef double abs_diff = 0;
    
    cdef double[:,:,:] timepoint_deltas = numpy.empty((num_timepoints, num_timepoints, num_features), dtype=numpy.double)

    # Zero the output
    for permutation in range(num_permutations):
        for feature in range(num_features):
            out_view[permutation, feature] = 0

    cdef int[:,:] indexes_for_timepoint = numpy.empty((num_timepoints, num_samples), dtype=numpy.int32)
    cdef int[:] num_reps_for_timepoint = numpy.zeros((num_timepoints), dtype=numpy.int32)
    # Group the columns by their timepoints
    for t in range(num_timepoints):
        num_reps_for_timepoint[t] = 0
    for i in range(num_samples):
        timepoint = timepoints[i]
        indexes_for_timepoint[timepoint, num_reps_for_timepoint[timepoint]] = i
        num_reps_for_timepoint[timepoint] += 1

    # Compute the absolute delta between any two timepoints
    # Only fill out above the diagonal of these comparisons: don't need both (i,j) and (j,i) or (i,i)
    for timepoint1 in range(num_timepoints):
        for timepoint2 in range(timepoint1+1, num_timepoints):
            for feature in range(num_features):
                total = 0
                for rep1 in range(num_reps_for_timepoint[timepoint1]):
                    for rep2 in range(num_reps_for_timepoint[timepoint2]):
                        idx1 = indexes_for_timepoint[timepoint1, rep1]
                        idx2 = indexes_for_timepoint[timepoint2, rep2]
                        abs_diff = abs(data_view[feature, idx1] - data_view[feature, idx2])
                        if abs_diff == abs_diff:
                            # Add to sum if abs_diff is non-NaN (skips if either replicate is NaN)
                            total += abs_diff
                timepoint_deltas[timepoint1, timepoint2, feature] = total

    # Now compute the statistic by going through each permutation
    for permutation in range(num_permutations):
        permuted_timepoints = timepoint_permutations_view[permutation]
        for timepoint1 in range(num_timepoints):
            for timepoint2 in range(timepoint1+1, num_timepoints):
                if (   (permuted_timepoints[timepoint1] + 1) % timepoints_per_cycle == permuted_timepoints[timepoint2]
                    or (permuted_timepoints[timepoint1] - 1) % timepoints_per_cycle == permuted_timepoints[timepoint2] ):
                    for feature in range(num_features):
                        out_view[permutation, feature] += timepoint_deltas[timepoint1, timepoint2, feature]
