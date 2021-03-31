import collections
import itertools
import math

import numpy
from . import util
from . import upside

try:
    import pyximport
    pyximport.install()
    from .total_delta import sum_abs_differences as _sum_abs_differences
    def sum_abs_differences(data, timepoints, timepoints_per_cycle, out, contains_nans=True):
        # C implementation always handles NaNs correctly by zeroing them out
        # So we discard the contains_nans param
        _sum_abs_differences(data, timepoints, timepoints_per_cycle, out)
except ImportError as e:
    print("Encountered error while attempting to import cython module.")
    print("Defaulting to slower python-based implementation.")
    print(e)
    def sum_abs_differences(data, timepoints, timepoints_per_cycle, out, contains_nans=True):
        ''' python implementation of sum_abs_differences '''
        N_FEATURES, N_SAMPLES = data.shape

        out[:,:] = 0
        for i, permuted_timepoints in enumerate(timepoints):
            indexes_for_timepoint = [[i for i,t in enumerate(permuted_timepoints) if (t % timepoints_per_cycle) == j]
                                        for j in range(timepoints_per_cycle)]
            for timepoint in range(timepoints_per_cycle):
                next_timepoint = (timepoint + 1) % timepoints_per_cycle
                # By putting the two timepoints in axes 1 and 2 respectively, the sum
                # is now over all pairs of values according to numpy broadcasting rules
                data1 = data[:, indexes_for_timepoint[timepoint]].reshape((N_FEATURES, -1, 1))
                data2 = data[:, indexes_for_timepoint[next_timepoint]].reshape((N_FEATURES, 1, -1))
                abs_diffs = numpy.abs(data1 - data2).sum(axis=(1,2))
                if contains_nans:
                    util.zero_nans(abs_diffs)
                out[i, :] += abs_diffs

# Number of permutations to take for permuted test statistics
N_PERMS = 100
# Number of permutations to compute at one go, reduce this number to reduce memory useage
N_PERMS_PER_RUN = 20

descriptive_stats = collections.namedtuple("DescriptiveStats", ["amplitude", "peak_time", "trough_time"])

### the main function of nitecap which encapsulates all the work
def main(data, timepoints, timepoints_per_cycle, N_PERMS = N_PERMS, output="minimal", repeated_measures=False):
    '''Identify circadian behavior in `data`

    `data` is an numpy array with the following format:
    Each row of data is a single feature with entries in the order
    time0_rep0 time0_rep1 .. time0_rep2 time1_rep0 time1_rep1 ...
    So that all replicates (if any) of the timepoints are clumped together and the timepoints are in ascending order

    timepoints is a list of timepoints (0,1,2...) corresponding to each column of `data`
    timepoints_per_cycle is the number of timepoints measured per cycle (eg: every four hours gives 6 timespoints per day)
    repeated_measures is whether the data is collected on the same subjects repeatedly. Leave as False if
        each measurement is independent

    If output == "minimal" then output (q,td) where:
    `q` is a numpy array with a q value
        (i.e. rejecting all null hypotheses for features with q < alpha controls the FDR at level alpha)
    `td` is a numpy array with the total delta statistics of each feature.
        Lower total_delta indicates more circadian behavior
    If output == "full" then output (q,td, perm_td) where:
    `perm_td` is a numpy array with total_delta statitics of features with permuted time points
            useful for diagnostics of the nitecap method on ones data and plotting results

    Technical replicates may be used, so long as all replicates within a single timepoint are either all technical
    replicates or are all biological replicates
    '''

    data = numpy.array(data)

    td, perm_td = nitecap_statistics(data, timepoints, timepoints_per_cycle, N_PERMS, repeated_measures=repeated_measures)
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
    #TODO: add an 'exhaustive' parameter for the case when we have enumerated all possible permutations
    # and therefore don't need the '+1's in the p/q values

    (N_PERMS, N_GENES) = perm_td.shape
    sort_order = numpy.argsort(td)

    # p-values of the (non-permuted) data
    ps = util.permutation_ps(td, perm_td, comparison="less")


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

def total_delta(data, timepoints, timepoints_per_cycle, contains_nans = "check", repeated_measures=False):
    # Data without permutations is expected to be 3 dimensional (timepoints, reps, genes)
    # so add a dimension to it represent that it is "one permutation" so the code is consistent
    if timepoints.ndim == 1:
        timepoints = timepoints.reshape( (1, *timepoints.shape) )
        no_permutations = True
    else:
        no_permutations = False

    if contains_nans == "check":
        contains_nans = numpy.isnan(data).any()

    data = data.astype("double")

    N_FEATURES, N_SAMPLES = data.shape
    N_PERMS, N_SAMPLES = timepoints.shape

    if repeated_measures == False:
        # Compute the usual (non-repeated measures statistic)
        ### COMPUTE IN C:
        total_delta = numpy.empty((N_PERMS, N_FEATURES), dtype="double")
        sum_abs_differences(data, timepoints, timepoints_per_cycle, total_delta, contains_nans)
        if contains_nans:
            # total_delta above counts a pair with a NaN as 0 difference
            # Need to renormalize by the number of pairings so that all genes are comparable
            # even if there are different numbers of NaNs in each

            # First, compute the number of pairs in the sum assuming nothing in none
            rep_counts = numpy.array([(timepoints == i).sum(axis=1) for i in range(timepoints_per_cycle)])
            rep_counts_shifted = numpy.concatenate([rep_counts[[-1],:], rep_counts[:-1,:]])
            possible_pairs = numpy.sum( rep_counts * rep_counts_shifted, axis=0).reshape((-1,1))

            # Compute the number of non-nans in each timepoint for each features
            # NOTE: we don't care about *which* permutation of timepoints we use for this
            # so just choose timepoints[0]
            indexes_for_timepoints = [[i for i,t in enumerate(timepoints[0]) if (t % timepoints_per_cycle) == j]
                                        for j in range(timepoints_per_cycle)]
            non_nan_per_timepoint =  numpy.array([numpy.sum(~numpy.isnan(data[:, indexes]), axis=1)
                                                    for indexes in indexes_for_timepoints])

            # Compute the average number of pairings across all possible permutations
            # I.e. we are computing:
            # sum_{i = 1...n} sum_{sigma in PermutationGroup_n} x_{sigma_i} x_{sigma_{i+1}}
            # where x_i is the number of non-nulls at timepoint i (in the identity permutation)
            # (and treating sigma_{n+1} = sigma_{1}, i.e. cyclic indexing)
            # This is proportional to the sum_{i = 1 ..n} sum_{j != i} x_i x_j
            # which is what we compute here and then average out among all permutations
            all_pairwise_products = numpy.sum(non_nan_per_timepoint, axis=0)**2 - numpy.sum(non_nan_per_timepoint**2, axis=0)
            avg_num_pairs = (all_pairwise_products / (timepoints_per_cycle-1)).reshape((1,-1))

            # Normalize by max-possible pairs (if no nans) and the average permutation amount (dropping actual nans)
            total_delta *= possible_pairs / avg_num_pairs
            #TODO: this could give NaN outputs if any timepoint has 0 non-nans
        ####

        # Now compute the normalization factor
        # NOTE: this computation assumes that all the permutations have the same median
        # i.e. that they really are permutations and not just unrelated data
        med = numpy.nanmedian(data, axis=1) #Median of each gene
        med_diffs = data - med[:, None]
        numpy.abs(med_diffs, out=med_diffs)
        if contains_nans:
            util.zero_nans(med_diffs)
        max_delta = numpy.sum( med_diffs, axis=1)
        # Given a normalization factor of 0, we'll get a warning below
        # So replace it with 1 since the result will have total_delta = 0 anyway
        max_delta[max_delta == 0.0] = 1.0

    else:
        raise NotImplementedError
        # Never had this working satisfactorily before and it is no longer applicable after the
        # switch from 4-dimensional data to 2-dimensional data plus 2-dimensional timepoints
        # the rest here is maintained for posterity

        # For repeated_measures we need to compute differently
        # 1) Take only the absolute differences of adjacent timepoints within the same replicate
        # 2) Normalize by taking sum of absolute differences between each value and median within the same replicate
        # This is a smaller compute (unless only 1 replicate) so we won't do it in C
        data_cycled = numpy.concatenate( (data[:,1:], data[:,:1]), axis=1 )
        diffs = numpy.abs(data - data_cycled)

        # Need to manually zero out the nans we get
        if contains_nans:
            number_nonnan = numpy.sum(numpy.isfinite(diffs), axis=(1,2))
            util.zero_nans(diffs)

        total_delta = numpy.sum(diffs, axis=(1,2))

        if contains_nans:
            # normalization factor for the missing values
            # Missing values give 0 diffs so we must account for that
            total_delta *= number_nonnan / (N_TIMEPOINTS * N_REPS)

        # Normalization across genes
        # by the absolute differences from the replicate's median value
        med = numpy.nanmedian(data[0], axis=0).reshape((1, N_REPS, N_FEATURES))
        med_diffs = numpy.abs(data[0] - med)
        if contains_nans:
            util.zero_nans(med_diffs)
        max_delta = numpy.sum(med_diffs, axis=(0,1))
        max_delta[max_delta == 0.0] = 1.0 # To avoid a warning, see above.

    statistic =  total_delta / max_delta
    if no_permutations:
        return statistic.reshape( (N_FEATURES) ) # If we were given a 1-dim timepoints array, return a 1-dim array
    else:
        return statistic

def nitecap_statistics(data, timepoints, timepoints_per_cycle, N_PERMS = N_PERMS, repeated_measures=False):
    ''' Compute total_delta statistic and permutation versions of this statistic

        `data` is data formatted as by reformat_data(data, timepoints_per_cycle, num_reps, num_cycles)
        `timepoints` is a list of timepoint values corresponding to each column of data
        `timepoints_per_cycle` is the number of timepoints per cycle
        `repeated_measures` is whether the data is from the same subjects repeatedly measured. Leave False
            if each measurement is independent.
        '''

    assert len(timepoints) == data.shape[1]

    N_FEATURES, N_SAMPLES = data.shape

    contains_nans = numpy.isnan(data).any()

    td = total_delta(data, timepoints, timepoints_per_cycle, contains_nans, repeated_measures=repeated_measures)

    # If the total number of permutations possible is less than N_PERMS
    # then we just run all possible distinct permutations, for a deterministic p-value
    # Distinct perms: since our statistic is independent of cyclic permutations and mirroring
    # we can count distinct perms by fixing the first timepoint and dividing by two
    num_perms_distinct = int(math.factorial(timepoints_per_cycle-1)/2)
    if N_PERMS >= num_perms_distinct:
        # Enumerate all permutations out at once, as indexes
        # Since statistic is independent of cyclic permutations, we can fix the first
        # timepoint. Since independent of mirroring, only need "ascending" permutations
        permutations = [[0] + list(p) for p in itertools.permutations(range(1,timepoints_per_cycle))
                            if p[0] < p[-1]]
        permutations = numpy.array(permutations)
        assert num_perms_distinct == len(permutations)
        N_PERMS = num_perms_distinct
    else:
        permutations = None

    # Run N_PERMS_PER_RUN permutations repeatedly until we get a total of N_PERMS
    num_perms_done = 0
    perm_td = numpy.empty((N_PERMS, N_FEATURES))
    while True:
        if num_perms_done >= N_PERMS:
            break

        # Number of permutations to do this time - usually is N_PERMS_PER_RUN
        num_perms = min(N_PERMS - num_perms_done, N_PERMS_PER_RUN)

        if permutations is not None:
            these_permutations = permutations[num_perms_done:num_perms_done+num_perms]
        else:
            # Pick random permutations
            these_permutations = numpy.array(
                [numpy.random.choice(timepoints_per_cycle, size=timepoints_per_cycle, replace=False)
                        for i in range(num_perms)])

        # Prepare the permuted data
        permuted_timepoints = numpy.array([permutation[timepoints] for permutation in these_permutations])

        # Actually compute the statistics
        perm_td[num_perms_done:num_perms_done+num_perms,:] = total_delta(data, permuted_timepoints, timepoints_per_cycle, contains_nans, repeated_measures=repeated_measures)

        num_perms_done += num_perms

    # Center the statistics for each feature
    meds = numpy.nanmedian(perm_td, axis=0)
    td = td - meds
    perm_td = perm_td - meds
    return td, perm_td

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

def descriptive_statistics(data, timepoints, timepoints_per_cycle, cycle_length=24):
    ''' Given data of shape (N_FEATURES, N_SAMPLES) and timepoints of shape (N_SAMPLES), compute the amplitude, peak time, and trough time of the data

    Estimates the underlying curve by a moving regression and takes peak and trough to estimate the amplitude
    '''
    (N_FEATURES, N_SAMPLES) = data.shape

    N_POINTS = 25

    ys = data.T
    xs = timepoints
    ts = numpy.linspace(0, timepoints_per_cycle, N_POINTS)  # Evaluate the moving average at evenly spaced points
    regression = util.moving_regression(xs, ys,  frac = 0.7, degree=2, period = timepoints_per_cycle,  regression_x_values = ts)

    peak_time = numpy.argmax(regression, axis=0)
    trough_time = numpy.argmin(regression, axis=0)
    peak = regression[peak_time,range(N_FEATURES)]
    trough = regression[trough_time,range(N_FEATURES)]

    amplitude = peak - trough

    return descriptive_stats(amplitude, peak_time * cycle_length / (N_POINTS - 1), trough_time * cycle_length  / (N_POINTS - 1))
