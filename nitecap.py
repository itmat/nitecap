import numpy
import pandas
import pylab
import scipy.stats
import util

# Number of permutations to take for permuted test statistics
N_PERMS = 100

# How many times to sample points when computing the statistic total_delta?
N_ITERS = 50

### the main function of nitecap which encapsulates all the work
def nitecap(data, timepoints_per_cycle, num_replicates, num_cycles, N_ITERS = N_ITERS, N_PERMS = N_PERMS, output="minimal"):
    '''Identify circadian behavior in `data`

    `data` is an numpy array with the following format:
    Each row of data is a single feature with entries in the order
    time0_rep0 time0_rep1 .. time0_rep2 time1_rep0 time1_rep1 ... 
    So that all replicates (if any) of the timepoints are clumped together and the timepoints are in ascending order

    timepoints_per_cycle is the number of timepoints measured per cycle (eg: every four hours gives 6 timespoints per day)
    num_replicates is the number of replicates at each timepoint
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

    td, perm_td, perm_data = nitecap_statistics(data_formatted, N_ITERS, N_PERMS)
    q = FDR(td, perm_td)
    if output == "full":
        return q, td, perm_td
    return q, td

def FDR(td, perm_td):
    '''Control the False Discovery Rate (FDR)

    Given any test statistic td and the same statistic computed on permuted data `perm_td`,
    compute the associated q values of rejecting all null hypotheses with td less than a cutoff
    '''
    (N_PERMS, N_GENES) = perm_td.shape
    sort_order = numpy.argsort(td)

    ps = (numpy.sum(perm_td <= td, axis=0) + 1)/ (perm_td.shape[0]+1)

    q = numpy.zeros(N_GENES)
    expected_false_discoveries = numpy.zeros(N_GENES)
    for i, gene in enumerate(sort_order):
        # We try rejecting the lowest (i+1) td-values and computing how many false rejections we expect
        # by assuming that any td-values we get after a random permutation must correspond to a null

        tentative_cutoff = td[gene]

        # Handle NaN values by giving them NaN q's
        if numpy.isnan(tentative_cutoff):
            q[gene] = numpy.nan
            continue

        # Simplest version
        #expected_false_discoveries[gene] = numpy.sum(perm_td <= tentative_cutoff) / N_PERMS

        # Weight each gene by it's original p-value and multiply by 2
        expected_false_discoveries[gene] = 2*numpy.sum((perm_td <= tentative_cutoff) * ps) / N_PERMS

        # Weight by any function of p and divide by it's integral from 0 to 1...
        #ps_okay = (ps > 0.25) & (ps < 0.75)
        #expected_false_discoveries[gene] = (2.0)*numpy.sum((perm_td <= tentative_cutoff) * ps_okay) / N_PERMS

        q[gene] = expected_false_discoveries[gene] / (i+1)

    # Make q's monotone increasing (step-up)
    for i, gene in enumerate(sort_order):
        q[gene] = numpy.min(q[sort_order[i:]])

    return q

def total_delta(data, contains_nans = False, N_ITERS = N_ITERS, median = False):
    # Compute Delta as total absolute differences for each of the replicate
    # Random choices of the points to compute for
    # Set contains_nans = True if data may contain nans (interpretted as missing data)
    # if instead is False, a marginally more efficient method is used that would propogate nans inappropriately
    # NOTE: assumes that NANs are the last of the reps else we will
    # if you are getting NANs, this could be why!

    (N_TIMEPOINTS, N_REPS, N_GENES) = data.shape

    # Choose random points (avoiding NANs if necessary
    if contains_nans:
        # want to choose non-nan points, so we only pick numbers up to the number of finite points
        # this work since we require NaNs to be in the back of the array (eg: by sorting data along axis=1 first)
        okay_pts = numpy.isfinite(data)
        num_okay = okay_pts.sum(axis=1).reshape( (N_TIMEPOINTS, N_GENES, 1) )
        all_pts = (numpy.random.random( (N_TIMEPOINTS, N_GENES, N_ITERS) )*num_okay).astype("int32")
    else:
        all_pts = numpy.random.choice( N_REPS, size=(N_TIMEPOINTS, N_GENES, N_ITERS) )

    num_iters = numpy.zeros(N_GENES)

    if median:
        deltas = numpy.zeros( (N_GENES,N_ITERS) )
    else:
        deltas = numpy.zeros( (N_GENES,) )
    
    for i in range(N_ITERS):
        pts = all_pts[:,:,i]
        d = data.swapaxes(0,1)
        selected = numpy.choose(pts, d) # Select on the 'rep' axis of data
        #selected = selected.reshape( (N_TIMEPOINTS, N_GENES) )
        diffs = numpy.abs(selected[1:] - selected[:-1])
        wrap_around_terms = numpy.abs(selected[-1] - selected[0])
        spans = numpy.max(selected, axis=0) - numpy.min(selected, axis=0)
        
        #valid = numpy.isfinite(spans)
        #num_iters += valid
        #deltas[valid] += (numpy.sum(diffs, axis=0)[valid] + wrap_around_terms[valid]) / spans[valid]

        if median:
            deltas[:,i] = (numpy.sum(diffs, axis=0) + wrap_around_terms) / spans
        else:
            deltas += (numpy.sum(diffs, axis=0) + wrap_around_terms) / spans

    if median:
        deltas = numpy.median(deltas, axis=1)
    else:
        deltas /= N_ITERS

    # TODO: reimplement NaN handling for the case when there are completely flat occurances
    # only happens if there is a value that every single timepoint has exactly in common
    # But this is common for low-expressed genes or other count data
    return deltas

def nitecap_statistics(data, N_ITERS = N_ITERS, N_PERMS = N_PERMS):
    ''' Compute total_delta statistic and permutation versions of this statistic '''

    contains_nans = numpy.isnan(data).any()
    if contains_nans:
        # Need to prep the data by moving all NaNs to the "back"
        # This is for the randomized selection of points for total_delta
        # Sorting (or rearranging) the reps doesn't make a difference and sorting puts NaNs at the end
        data = numpy.sort(data, axis=1)

    #perm_data = numpy.array([permute_and_reflect(data) for i in range(N_PERMS)])
    perm_data = numpy.array([permute_timepoints(data) for i in range(N_PERMS)])

    td = total_delta(data, contains_nans, N_ITERS)
    perm_td = numpy.array([total_delta(perm_data[i], contains_nans, N_ITERS) for i in range(N_PERMS)])

    # Center the statistics for each feature
    meds = numpy.nanmedian(perm_td, axis=0)
    td = td - meds
    perm_td = perm_td - meds
    return td, perm_td, perm_data

def permute_timepoints(data):
    # Take data with shape (N_timespoints, N_reps)
    # and return a permutation which randomizes the timepoints
    # but not the samples with a timepoint - replicates stay together
    new_data = data.copy()
    numpy.random.shuffle(new_data)
    return new_data

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
    (num_timepoints, num_replicates*num_cycles, num_features)
    Assumption is that the order of samples is with increasing time and with replicates of a single timepoint placed together
    '''
    # Put the data into the shape of a 3d array with dimensions [timepoints, replicates, features]
    data_formatted = data.reshape( (-1, timepoints_per_cycle*num_cycles, num_replicates) ).swapaxes(0,1).swapaxes(1,2)

    # For each cycle, fold the repeated cycles over on top of each other
    # i.e. now the shape will be (timepoints_per_cycle, num_replicates*num_cycles, num_features)
    data_formatted = numpy.concatenate( [data_formatted[i*timepoints_per_cycle:(i+1)*timepoints_per_cycle,:,:]
                                            for i in range(num_cycles)], axis=1 )
    return data_formatted
