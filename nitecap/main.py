import collections

import numpy
from . import util

try:
    from .total_delta import sum_abs_differences as _sum_abs_differences
    def sum_abs_differences(data, out, contains_nans=True):
        # C implementation always handles NaNs correctly by zeroing them out
        # So we discard the contains_nans param
        _sum_abs_differences(data, out)
except ImportError as e:
    def sum_abs_differences(data, out, contains_nans=True):
        (N_PERMS, N_TIMEPOINTS, N_REPS, N_GENES) = data.shape
        data_A = data.reshape((N_PERMS, N_TIMEPOINTS, N_REPS, 1, N_GENES))
        data_B = data.reshape((N_PERMS, N_TIMEPOINTS, 1, N_REPS, N_GENES))
        # cycle data_B one step over so that we'll compare time 1 in A to time 2 in B
        data_B = numpy.concatenate( (data_B[:,1:], data_B[:,:1]), axis=1 )

        # Sum all the differences across all rep-rep pairs across all timepoints
        diffs = data_A - data_B
        numpy.abs(diffs, out=diffs)

        # Need to manually zero out the nans we get
        if contains_nans:
            util.zero_nans(diffs)

        numpy.sum(diffs, axis=(1,2,3), out=out)

# Number of permutations to take for permuted test statistics
N_PERMS = 100
# Number of permutations to compute at one go, reduce this number to reduce memory useage
N_PERMS_PER_RUN = 20

descriptive_stats = collections.namedtuple("DescriptiveStats", ["amplitude", "peak_time", "trough_time"])

### the main function of nitecap which encapsulates all the work
def main(data, timepoints_per_cycle, num_replicates, num_cycles, N_PERMS = N_PERMS, output="minimal"):
    '''Identify circadian behavior in `data`

    `data` is an numpy array with the following format:
    Each row of data is a single feature with entries in the order
    time0_rep0 time0_rep1 .. time0_rep2 time1_rep0 time1_rep1 ...
    So that all replicates (if any) of the timepoints are clumped together and the timepoints are in ascending order

    timepoints_per_cycle is the number of timepoints measured per cycle (eg: every four hours gives 6 timespoints per day)
    num_replicates is the number of replicates at each timepoint, or is a list of replicates at each timepoint
    num_cycles is the number of cycles worth of data present

    If output == "minimal" then output (q,td) where:
    `q` is a numpy array with a q value
        (i.e. rejecting all null hypotheses for features with q < alpha controls the FDR at level alpha)
    `td` is a numpy array with the total delta statistics of each feature.
        Lower total_delta indicates more circadian behavior
    If output == "full" then output (q,td, perm_td) where:
    `perm_td` is a numpy array with total_delta statitics of features with permuted time points
            useful for diagnostics of the nitecap method on ones data and plotting results

    The assumption is that all timepoints are independent samples (no repeated measures on the same individual)
    Technical replicates may be used, so long as all replicates within a single timepoint are either all technical
    replicates or are all biological replicates
    '''

    data = numpy.array(data)
    data_formatted = reformat_data(data, timepoints_per_cycle, num_replicates, num_cycles)

    td, perm_td = nitecap_statistics(data_formatted, num_cycles, N_PERMS)
    q, p = FDR(td, perm_td)
    if output == "full":
        return q, td, perm_td
    return q, td, p

def FDR(td, perm_td, single_tailed=True):
    '''Control the False Discovery Rate (FDR)

    Given any test statistic td and the same statistic computed on permuted data `perm_td`,
    compute the associated q values of rejecting all null hypotheses with td less than a cutoff
    Also returns the p-values of each hypothesis
    If the test is single-tailed (like Nitecap), set single_tailed=True, otherwise single_tailed = False
    will give more accurate estimates for double-tailed statistics
    '''
    (N_PERMS, N_GENES) = perm_td.shape
    sort_order = numpy.argsort(td)

    # p-values of the (non-permuted) data
    ps = (numpy.sum(perm_td <= td, axis=0) + 1)/ (perm_td.shape[0]+1)


    # Want to sum how many permutations end up less than a given cutoff
    # so sort them all so that they can be counted efficiently
    perm_td_sort_order = numpy.argsort(perm_td, axis=None)
    perm_td_sorted = perm_td.flat[perm_td_sort_order]

    # And give each permutation the p-value of it's actual (non-permuted) data
    # but put them in the same order as the statistics above, so that we can weight by this p
    ps_sorted = numpy.broadcast_to(ps, (N_PERMS, N_GENES))# Each permutation gets the same p-value
    ps_sorted = ps_sorted.flat[perm_td_sort_order]

    # Compute weights of each gene from their p-values
    # low p-value genes do not count as much towards being a 'null' gene
    # when computing the number of nulls below a cutoff
    if single_tailed:
        # Convert p-values of a single-tailed distribution into
        # p-values for a double-tailed distribution so that p-values near 1
        # are not treated as 'extremely null' in the weighting
        weights = 30*(ps_sorted**2 * (1-ps_sorted)**2)
    else:
        weights = 2*ps_sorted

    # Sum up all the p-values in order
    weights_sorted_cumsum = numpy.concatenate( ([0], numpy.cumsum(weights)) )

    # Compute the number of gene-permutation combinations below any given cutoff td
    num_below_cutoff = numpy.searchsorted(perm_td_sorted, td[sort_order], side="right")

    # Estimate the number of nulls among those below the cutoff by summing their p values and multiplying by 2
    expected_false_discoveries = weights_sorted_cumsum[num_below_cutoff] / (N_PERMS + 1)

    # Compute q values by dividing by the number of rejected genes at each td
    q = (expected_false_discoveries+1) / numpy.arange(1, 1+N_GENES)

    # Make q's monotone increasing (step-up)
    # i.e. if a later gene (with worse td) has a better q, then we use it's q
    # so take the minimum of all q's that are later than your own
    q = numpy.minimum.accumulate( q[::-1] )[::-1]

    # Return the q's in the order they came in, not in the order of increasing td (i.e. sort_order)
    unsort_order = numpy.argsort(sort_order)
    return q[unsort_order], ps

def total_delta(data, contains_nans = "check"):
    # Data without permutations is expected to be 3 dimensional (timepoints, reps, genes)
    # so add a dimension to it represent that it is "one permutation" so the code is consistent
    if data.ndim == 3:
        data = data.reshape( (1, *data.shape) )
        no_permutations = True
    else:
        no_permutations = False

    if contains_nans == "check":
        contains_nans = numpy.isnan(data).any()

    data = data.astype("double")

    (N_PERMS, N_TIMEPOINTS, N_REPS, N_GENES) = data.shape

    ### COMPUTE IN C:
    total_delta = numpy.empty((N_PERMS, N_GENES), dtype="double")
    sum_abs_differences(data, total_delta)
    if contains_nans:
        # total_delta above counts a pair with a NaN as 0 difference
        # Need to renormalize by the number of pairings so that all genes are comparable
        # even if there are different numbers of NaNs in each
        possible_pairs = N_TIMEPOINTS * N_REPS * N_REPS
        non_nan_per_timepoint =  numpy.sum(~numpy.isnan(data[0]), axis=1)

        # Compute the average number of pairings across all possible permutations
        # I.e. we are computing:
        # sum_{i = 1...n} sum_{sigma in PermutationGroup_n} x_{sigma_i} x_{sigma_{i+1}}
        # where x_i is the number of non-nulls at timepoint i (in the identity permutation)
        # (and treating sigma_{n+1} = sigma_{1}, i.e. cyclic indexing)
        # This is proportional to the sum_{i = 1 ..n} sum_{j != i} x_i x_j
        # which is what we compute here and then average out among all permutations
        all_pairwise_products = numpy.sum(non_nan_per_timepoint)**2 - numpy.sum(non_nan_per_timepoint**2)
        avg_num_pairs = all_pairwise_products / (N_TIMEPOINTS-1)

        total_delta *= possible_pairs / avg_num_pairs
        #TODO: this could give NaN outputs if any timepoint has 0 non-nans
    ####

    # Now compute the normalization factor
    # NOTE: this computation assumes that all the permutations have the same median
    # i.e. that they really are permutations and not just unrelated data
    med = numpy.nanmedian(data[0], axis=(0,1)).reshape((1, 1, N_GENES)) #Median of each gene
    med_diffs = data[0] - med
    numpy.abs(med_diffs, out=med_diffs)
    if contains_nans:
        util.zero_nans(med_diffs)
    max_delta = numpy.sum( med_diffs, axis=(0,1) )
    # Given a normalization factor of 0, we'll get a warning below
    # So replace it with 1 since the result will have total_delta = 0 anyway
    max_delta[max_delta == 0.0] = 1.0

    statistic =  total_delta / max_delta
    if no_permutations:
        return statistic.reshape( (N_GENES) ) # If we were given a 3-dim array, return a 1-dim array
    else:
        return statistic

def nitecap_statistics(data, num_cycles = 1, N_PERMS = N_PERMS):
    ''' Compute total_delta statistic and permutation versions of this statistic

        `data` is data formatted as by reformat_data(data, timepoints_per_cycle, num_reps, num_cycles)
        `num_cylces` is the number of cycles in the data, eg 2 if data is 48hours
        '''

    (N_TIMEPOINTS, N_REPS, N_GENES) = data.shape


    contains_nans = numpy.isnan(data).any()

    data_folded = fold_days(data, num_cycles)
    td = total_delta(data_folded, contains_nans)

    # Run N_PERMS_PER_RUN permutations repeatedly until we get a total of N_PERMS
    num_perms_done = 0
    perm_td = numpy.empty((N_PERMS, N_GENES))
    while True:
        if num_perms_done >= N_PERMS:
            break

        num_perms = min(N_PERMS - num_perms_done, N_PERMS_PER_RUN)
        perm_data = permute_timepoints(data, num_perms)
        perm_data_folded = fold_days(perm_data, num_cycles)

        perm_td[num_perms_done:num_perms_done+num_perms,:] = total_delta(perm_data_folded, contains_nans)

        num_perms_done += num_perms

    # Center the statistics for each feature
    meds = numpy.nanmedian(perm_td, axis=0)
    td = td - meds
    perm_td = perm_td - meds
    return td, perm_td

def permute_timepoints(data, N_PERMS = None):
    # Take data with shape (N_timespoints, N_reps)
    # and return a permutation which randomizes the timepoints
    # but not the samples within a timepoint - replicates stay together
    if N_PERMS is None:
        new_data = data.copy()
        numpy.random.shuffle(new_data)
        return new_data
    else:
        perm_data = numpy.broadcast_to(data, (N_PERMS,*data.shape)).copy()
        # Shuffle (in place) each "permutation" along timepoints
        [numpy.random.shuffle(perm_data[i]) for i in range(N_PERMS)]
        return perm_data

def permute_and_reflect(data):
    # permutes timepoints and reflects points randomly around the median
    (N_TIMEPOINTS, N_REPS, N_GENES) = data.shape
    permuted = permute_timepoints(data)

    grand_median = numpy.nanmedian(data, axis=[0,1])
    reflections = numpy.random.randint(2, size = (N_TIMEPOINTS,1,N_GENES))
    result = permuted - 2*(permuted - grand_median) * reflections
    return result

def reformat_data(data, timepoints_per_cycle, num_replicates, num_cycles):
    '''Reformats data into the expected shape for nitecap's internal use

    Turns a 2D array of shape (num_features, num_samples) into a 3D array of shape
    (num_timepoints*num_cylces, num_replicates, num_features)
    Assumption is that the order of samples is with increasing time and with replicates of a single timepoint placed together

    If the number of replicates varies between timepoints, num_replicates should be a list
    of the number of replicates at each timepoint. The formatted data will include NaN columns
    so that the resulting array is rectangular.
    '''

    num_features, _ = data.shape

    # If the number of replicates varies between timepoints, then we need to put nans in to fill the missing gaps
    if isinstance(num_replicates, (list, tuple)):
        num_timepoints = timepoints_per_cycle * num_cycles
        if len(num_replicates) != num_timepoints:
            raise ValueError(f"num_replicates must be equal in length to the expected number of timepoints {num_timepoints}, instead is length {len(num_replicates)}")
        if min(num_replicates) < 0:
            raise ValueError("num_replicates must have at least 1 replicate per timepoint")

        max_num_replicates = max(num_replicates)

        # Fill the 'missing' replicate columns with nans
        existing_columns = [i*max_num_replicates + j for i in range(num_timepoints)
                                                     for j in range(max_num_replicates)
                                                     if j < num_replicates[i]]
        full_data = numpy.full((num_features, num_timepoints*max_num_replicates), float("nan"))
        full_data[:,existing_columns] = data
        data = full_data

        num_replicates = max_num_replicates

    # Put the data into the shape of a 3d array with dimensions [timepoints, replicates, features]
    data_formatted = data.reshape( (-1, timepoints_per_cycle*num_cycles, num_replicates) ).swapaxes(0,1).swapaxes(1,2)

    return data_formatted

def fold_days(data, num_cycles):
    # Take data of shape (num_timepoints * num_cycles, num_replicates, num_features)
    # such as from reformat_data, and fold the days ontop of eachother so that it is of shape
    # (num_timepoints, num_replicates * num_cycles, num_features)
    # Also supports data of shape (num_perms, num_timepoints * num_cycles, num_replicates, num_features)
    timepoints_per_cycle = data.shape[-3] // num_cycles
    data_folded = numpy.concatenate( [data[...,i*timepoints_per_cycle:(i+1)*timepoints_per_cycle,:,:]
                                            for i in range(num_cycles)], axis=data.ndim-2 )
    return data_folded

def descriptive_statistics(data, num_cycles=1, cycle_length=24):
    ''' Given data of shape (N_TIMEPOINTS, N_REPS, N_GENES) compute the amplitude, peak time, and trough time of the data

    Estimates the underlying curve by a moving regression and takes peak and trough to estimate the amplitude
    '''
    (N_TIMEPOINTS, N_REPS, N_GENES) = data.shape

    N_POINTS = 25

    data = fold_days(data, num_cycles)

    ys = data.reshape( (N_TIMEPOINTS * N_REPS, N_GENES) )
    xs = numpy.repeat(numpy.arange(N_TIMEPOINTS), N_REPS)
    ts = numpy.linspace(0, N_TIMEPOINTS, N_POINTS)  # Evaluate the moving average at evenly spaced points
    regression = util.moving_regression(xs, ys,  frac = 0.7, degree=2, period = N_TIMEPOINTS,  regression_x_values = ts)

    peak_time = numpy.argmax(regression, axis=0)
    trough_time = numpy.argmin(regression, axis=0)
    peak = regression[peak_time,range(N_GENES)]
    trough = regression[trough_time,range(N_GENES)]

    amplitude = peak - trough

    return descriptive_stats(amplitude, peak_time * cycle_length / (N_POINTS - 1), trough_time * cycle_length  / (N_POINTS - 1))
