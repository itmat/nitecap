import numpy

def BH_FDR(ps):
    ''' Benjamini-Hochberg FDR control

    Converts p values to q values'''
    # For the purposes of comparison, an implementation of Benjamini Hochberg correction
    sort_order = numpy.argsort(ps)

    adjusted = numpy.zeros(ps.shape)
    adjusted[sort_order] = numpy.array(ps)[sort_order]*len(ps)/numpy.arange(1,len(ps)+1)

    # Make monotone
    for i, r in enumerate(sort_order):
        adjusted[r] = min(numpy.min(adjusted[sort_order[i:]]), 1)

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

    # Sort points
    for i,x in enumerate(regression_x_values):
        distances = numpy.abs(xs - x)

        tricube_distance = (1 - (distances / weight_radius )**3)**3
        tricube_distance[distances > weight_radius] = 0
        weights = tricube_distance.reshape((-1,1))

        # Perform weighted-least-squares regression
        weighted_ys = weights * ys
        weighted_predictors = weights * predictors
        coeffs, residuals, rank, singular_values = numpy.linalg.lstsq( weighted_predictors, weighted_ys, rcond=None)

        local_predictor = numpy.array([x**j for j in range(degree+1)]).reshape((1,-1))
        regression_value =  numpy.dot(local_predictor, coeffs)

        plt_x  = numpy.linspace(x-0.2*weight_radius,x+0.2*weight_radius,21)
        plt_y = [numpy.dot(numpy.array([x_**j for j in range(degree+1)]).reshape((1,-1)), coeffs ).reshape((-1,)) for x_ in plt_x]

        regression_values[i] = regression_value
    return regression_values
