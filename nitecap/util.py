import numpy
import scipy.stats

def BH_FDR(ps):
    ''' Benjamini-Hochberg FDR control

    Converts p values to q values'''
    # For the purposes of comparison, an implementation of Benjamini Hochberg correction
    sort_order = numpy.argsort(ps)

    adjusted = numpy.zeros(ps.shape)
    adjusted[sort_order] = numpy.array(ps)[sort_order]*len(ps)/numpy.arange(1,len(ps)+1)

    # Make monotone, skipping NaNs
    m = 1;
    for i, r in enumerate(sort_order[::-1]):
        if numpy.isfinite(adjusted[r]):
            m = min(adjusted[r], m)
            adjusted[r] = m

    return adjusted # the q-values

def FWER(tds, perm_tds):
    ''' Non-parametric FWER control through permutations

    Implements Westfall and Young (1993)'s FWER control method
    '''
    (N_PERMS, N_GENES) = perm_tds.shape

    sort_order = numpy.argsort(tds)

    # FWER (Westfall + Young 1993)
    p_hats = numpy.ones(N_GENES)
    for i, gene in enumerate(sort_order):
        p = 0
        for j in range(N_PERMS):
            perm_td = perm_tds[j]

            # For FWER control, compute genes at or higher than rank i
            any_higher_are_below_cutoff = numpy.any(perm_td[sort_order[i:]] <= tds[gene])
            p += 1/N_PERMS if any_higher_are_below_cutoff else 0

        p_hats[gene] = p
        p_hats[gene] = p_hats[sort_order[:i+1]].max() # make monotone
    return p_hats

def zero_nans(array):
    ''' Sets all nans in a numpy array to zero, works in-place

    Faster than numpy.nan_to_num, doesn't interfere with infinities
    and has a more descriptive name
    '''

    nans = numpy.isnan(array)
    array[nans] = 0

def moving_regression(xs, ys, frac, degree=2, period=None, regression_x_values = None):
    '''
    Compute moving regression, smoothing the data

    `xs` is a 1-D array of x-values
    `ys` is a 1-D or 2-D array of y-values, with the first axis matching the length of `xs`
    `frac` is the fraction of the total x-range (or period, if not None) to use in each regression
    `degree` is the degree of the regression
    `period` = None if the data is not assumed to be periodic, otherwise period must be
            must be the desired period of the regression
    `regression_x_values` is an array of x-values that the regressions will be evaluated at
            if None, then `xs` is used (default)

    returns:
    `regression_values` an array of the y-values of the regressions for each point
            of `regression_x_values`. If `ys` is  2-dimensional, then regression_values is too
            and has second axis equal to the second axis of `ys`
    '''

    assert xs.ndim == 1
    assert ys.ndim <= 2
    assert ys.shape[0] == xs.shape[0]

    # Convert 1-dim to 2-dim ys
    if ys.ndim == 1:
        ys.shape = (*ys.shape, 1)

    if regression_x_values is None:
        regression_x_values = xs.copy()
    regression_values = numpy.empty((regression_x_values.shape[0], ys.shape[1]))

    if period is not None:
        # Duplicate ys to cover a range of at least two extra periods on either end
        # assumign that the data is actually periodic

        # First, force all x-values to be within the interval [0,period)
        xs = xs % period
        regression_x_values = regression_x_values % period

        # Now duplicate this period below and above
        xs = numpy.concatenate( (xs - period, xs, xs + period), axis=0)
        ys = numpy.concatenate( (ys, ys, ys), axis = 0)
        diameter = period
    else:
        diameter = numpy.max(xs) - numpy.min(xs)

    weight_radius = diameter * frac /2

    # Matrix of values 1, x, x^2, x^3...
    predictors = xs.reshape((-1,1)) ** numpy.arange(degree+1).reshape((1,-1))

    # We need to handle nan's if present (also masks out infinities - maybe not desirable)
    finite_mask = numpy.isfinite(ys)
    contains_nans = not numpy.all(finite_mask)

    # Sort points
    for i,x in enumerate(regression_x_values):
        distances = numpy.abs(xs - x)

        tricube_distance = (1 - (distances / weight_radius )**3)**3
        tricube_distance[distances > weight_radius] = 0
        weights = tricube_distance.reshape((-1,1))

        # Perform weighted-least-squares regression
        weighted_ys = weights * ys
        weighted_predictors = weights * predictors

        # Linear regression
        if not contains_nans:
            # Without NaN's, linear regression is easy
            coeffs, residuals, rank, singular_values = numpy.linalg.lstsq( weighted_predictors, weighted_ys, rcond=None)
        else:
            # With NaNs, we have to be careful
            # Unfortunately this procedure is less numerically stable since it
            # computes the Gramian A^T A and so squares the condition number
            # Idea is that we just need to mask out any nan values, but need to do it on both
            # sides of the equation AX = B
            # Solving by A^T A X = A^T B but with the mask becomes A^T M A X = A^T M B
            # Based on http://alexhwilliams.info/itsneuronalblog/2018/02/26/censored-lstsq/
            A = weighted_predictors[numpy.newaxis,:,:]
            A_T = A.swapaxes(1,2)
            M = (finite_mask.T)[:,:,numpy.newaxis]
            B = (weighted_ys.T)[:,:,numpy.newaxis]
            B[~M] = 0 # Replace nan's with zeros in B
            # so B is now M * B, but can't just multiply since 0 * nan = nan not 0

            # TODO: these can be rewritten as an einsum and will probably speed up
            #       though surprisingly it's comparable to linalg.lstsq in speed already
            gramian = A_T @ (M * A)
            right_hand_side = A_T @ B
            try:
                coeffs = numpy.linalg.solve(gramian, right_hand_side)
            except numpy.linalg.LinAlgError:
                # Singular matrix, can't solve.
                # Happens, for example, if too many timepoints (all?) are NaN
                # We'll just spit out zero here then, for better or worse
                coeffs = numpy.zeros((degree+1,1))

        local_predictor = numpy.array([x**j for j in range(degree+1)]).reshape((1,-1))
        regression_value =  numpy.dot(local_predictor, coeffs)

        regression_values[i] = regression_value.flatten()
    return regression_values

def anova(data):
    '''
    Preform one-way ANOVA on the given data

    data is assumed to be an array of shape (N_TIMEPOINTS, N_REPS, N_GENES), see nitecap.reformat_data.
    Return value is of shape (N_GENES), with the p-value of each gene (or feature) in the array.
    '''
    (N_TIMEPOINTS, N_REPS, N_GENES) = data.shape

    if N_REPS == 1:
        raise ValueError("Cannot perform ANOVA on datasets without any replicates")
    
    anova_p = numpy.empty(N_GENES)

    # Check for nans
    finite_mask = numpy.isfinite(data)
    contains_nans = not numpy.all(finite_mask)
    
    # Unfortunately, no built-in better way to do ANOVA on repeated experiments in Scipy
    for i in range(N_GENES):
        row = data[:,:,i]

        if contains_nans:
            # Remove non-nans
            row = [row[j,:][finite_mask[j,:,i]]
                    for j in range(N_TIMEPOINTS)]

        p = scipy.stats.f_oneway(*row)[1]
        anova_p[i] = p
    return anova_p
