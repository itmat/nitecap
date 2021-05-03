# cython: language_level=3
import cython
import numpy

@cython.cdivision(True) # Use c-style % operator (always have positive values)
def sum_abs_differences(data_in, timepoints, int timepoints_per_cycle, data_out):
    ''' takes in numpy array of data_in of shape (N_FEATURES, N_SAMPLES) and timpepoints of shape (N_PERMUTATIONS, N_SAMPLES) mapping each column of data_in to the its corresponding timepoint
    Writes out to data_out of shape (N_PERMUTATIONS, N_FEATURES) the sum of the absolute differences of each
    sample from all the samples in adjacent timepoints for each feature and timepoint permutations
    '''
    # Enforce the necessary array shapes
    assert len(data_in.shape) == 2, "data_in should have 2 dimensions"
    assert len(timepoints.shape) == 2, "timepoints should have 2 dimensions"
    assert len(data_out.shape) == 2, "data_out should have 2 dimensions"
    assert data_in.shape[0] == data_out.shape[1], "data_in and data_out need to match size"
    assert data_in.shape[1] == timepoints.shape[1], "data_in and timepoints need to match in size"
    assert timepoints.shape[0] == data_out.shape[0], "data_out and timepoints need to match in size"
    #assert data_in.dtype == float, "data_in must by float type"
    #assert data_out.dtype == float, "data_out must be float type"
    #assert timepoints.dtype == int, "timepoints must be integer type"
    assert timepoints.min() >= 0, "timepoints cannot have values less than 0"
    assert timepoints.max() < timepoints_per_cycle, "timepoints cannot have values larger than timepoints_per_cycle-1"

    cdef Py_ssize_t num_features = data_in.shape[0]
    cdef Py_ssize_t num_samples = data_in.shape[1]
    cdef Py_ssize_t num_permutations = timepoints.shape[0]
    cdef Py_ssize_t num_timepoints = timepoints_per_cycle

    # cdef the indexes/iterators we use later so type is known
    cdef Py_ssize_t timepoint, next_timepoint, feature
    cdef Py_ssize_t rep1, rep2
    cdef Py_ssize_t idx1, idx2

    # Make views of the numpy array
    cdef double[:, :] data_view = data_in
    cdef double[:, :] out_view = data_out
    cdef int[:,:] timepoints_view = timepoints

    cdef double total = 0;
    cdef double abs_diff = 0;
    
    # These hold the info about which indexes correspond to a timepoint
    # i.e. `timepoints` arg maps index->timepoint but
    # these indexes_for_timepoint maps timepoint->index
    cdef int[:,:] indexes_for_timepoint = numpy.empty((timepoints_per_cycle, num_samples), dtype=numpy.int32)
    cdef int[:] num_reps_for_timepoint = numpy.zeros((timepoints_per_cycle), dtype=numpy.int32)

    for permutation in range(num_permutations):
        permuted_timepoints = timepoints_view[permutation]

        # Group the columns by their timepoints
        for t in range(timepoints_per_cycle):
            num_reps_for_timepoint[t] = 0
        for i in range(num_samples):
            timepoint = permuted_timepoints[i]
            indexes_for_timepoint[timepoint, num_reps_for_timepoint[timepoint]] = i
            num_reps_for_timepoint[timepoint] += 1

        # Zero the output
        for feature in range(num_features):
            out_view[permutation, feature] = 0

        # Compute the abs differences
        for timepoint in range(num_timepoints):
            next_timepoint = (timepoint + 1) % timepoints_per_cycle
            for feature in range(num_features):
                total = 0
                # Take two replicate from adjacent timepoints
                for rep1 in range(num_reps_for_timepoint[timepoint]):
                    for rep2 in range(num_reps_for_timepoint[next_timepoint]):
                        idx1 = indexes_for_timepoint[timepoint, rep1]
                        idx2 = indexes_for_timepoint[next_timepoint, rep2]
                        abs_diff = abs(data_view[feature, idx1] - data_view[feature, idx2])
                        if abs_diff == abs_diff:
                            # Add to sum if abs_diff is non-NaN (skips if either replicate is NaN)
                            total += abs_diff
                out_view[permutation, feature] += total
