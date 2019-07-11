import numpy
import scipy.stats
import statsmodels.api as sm
from numpy import cos, sin

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

def permutation_ps(tds, perm_tds, comparison="less"):
    '''
    Compute p-values for a given statistic and permutation values of that statistic

    If `comparison` is `less` then we count occurances where permutations are smaller than (or equal to)
    the non-permuted statistic. Otherwise, we check for permutations that are larger than (or equal to).
    '''

    if comparison == "less":
        return (numpy.sum(perm_tds <= tds, axis=0) + 1)/ (perm_tds.shape[0]+1)
    else:
        return (numpy.sum(perm_tds >= tds, axis=0) + 1)/ (perm_tds.shape[0]+1)

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

    # Iterate over all the points that we want regression value for
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
            # Solving by A^T A X = A^T B but with the mask becomes A^T (M x A) X = A^T (M x B)
            # where 'x' means the point-wise multiplication
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
                # Try the fastest way first, works if gramian is invertible for all features
                coeffs = numpy.linalg.solve(gramian, right_hand_side)
            except numpy.linalg.LinAlgError as e:
                # Singular matrix, can't solve.
                # Happens, for example, if too many timepoints (nearly all) are just NaN
                # This can happen if ANY feature has nearly all NaNs
                # So now we need to now do each feature individually, so that OK features are still handled
                coeffs = numpy.empty(right_hand_side.shape)
                for j in range(len(gramian)):
                    try:
                        coeffs[j] = numpy.linalg.solve(gramian[j], right_hand_side[j])
                    except numpy.linalg.LinAlgError:
                        # This was a problem feature, so we NaN it but not the others
                        coeffs[j] = float("NaN")

            # Even when the gramian is invertible, we might have extremely unstable results if
            # the only weighted points are very far away (eg: most timepoints are NaN and the
            # only non-nan are far away on just one side), then the regression can go crazy by extrapolating
            # So just NaN out any such coeffs
            masked_weights = (M * tricube_distance[numpy.newaxis,:,numpy.newaxis])
            highest_weight = numpy.nanmax(masked_weights, axis=1).flatten()
            print(masked_weights.shape, highest_weight.shape, coeffs.shape)
            coeffs[highest_weight < 0.8] = float("NaN") # Arbitrary tricube distance cutoff of 0.8, about 0.4 radii away

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

def two_way_anova(num_reps_A, data_A, num_reps_B, data_B):
    '''
    Perform two-way ANOVA between two conditions, A and B

    `num_replicates_A` is a list of integers indicating how many replicates there are from each timepoint in dataset A
    `data_A` is a numpy array of shape (num_features, num_samples) where num_samples = sum(num_replicates_A)
            containing the values of the condition A
    `num_replicates_B` is a list of integers indicating how many replicates there are from each timepoint in dataset B
    `data_B` is a numpy array of shape (num_features, num_samples) where num_samples = sum(num_replicates_B)
            containing the values of the condition B
    '''

    assert len(num_reps_A) == len(num_reps_B)
    assert data_A.shape[0] == data_B.shape[0]

    # Factor variables for the two replicates
    timepoints_A = [i for i, num_reps in enumerate(num_reps_A) for j in range(num_reps)]
    timepoints_B = [i for i, num_reps in enumerate(num_reps_B) for j in range(num_reps)]

    # Condition variables for the concatenated datasets
    timepoints = sm.tools.categorical(numpy.array(timepoints_A + timepoints_B), drop=True).T
    dataset = [0 for _ in timepoints_A] + [1 for _ in timepoints_B]
    intercept = [1 for _ in dataset]
    interaction = numpy.array(dataset)*timepoints
    full_model = numpy.vstack( (timepoints, dataset, interaction, intercept) )
    restricted_model = numpy.vstack( (timepoints, dataset, intercept) )

    combined_datasets = numpy.concatenate((data_A, data_B), axis=1)

    p_values = numpy.empty(combined_datasets.shape[0])
    for i in range(combined_datasets.shape[0]):
        full_fit = sm.OLS(combined_datasets[i], full_model.T).fit()
        restricted_fit = sm.OLS(combined_datasets[i], restricted_model.T).fit()

        f, p, df = full_fit.compare_f_test(restricted_fit)
        p_values[i] = p

    return p_values

def cosinor_analysis(num_reps_A, data_A, num_reps_B, data_B):
    '''
    Perform tests using a Cosinor (sinusoidal least-squares fit) method.

    `num_replicates_A` is a list of integers indicating how many replicates there are from each timepoint in dataset A
    `data_A` is a numpy array of shape (num_features, num_samples) where num_samples = sum(num_replicates_A)
            containing the values of the condition A
    `num_replicates_B` is a list of integers indicating how many replicates there are from each timepoint in dataset B
    `data_B` is a numpy array of shape (num_features, num_samples) where num_samples = sum(num_replicates_B)
            containing the values of the condition B

    returns:
        p-values for equality of amplitude between data sets
        p-values for equality of acrophase (peak time)

    Tests performed in this method are based off the following publication:
    Bingham, Arbogast, Cornelissen Guillaume, Lee, Halberg "Inferential Statistical Methods for Estimating and Comparing Cosinor Parameters" 1982
    In particular, see equations 49 and 50, in the case where k=2 using the t-test versions

    Assumes equality of variances in data_A and data_B
    If the design is balanced (same # replicates in boths data_A and data_B) then equality of
    variances is somewhat less important.
    '''

    assert data_A.shape[0] == data_B.shape[0]
    num_features = data_A.shape[0]

    # Number of samples in each dataset
    N_A = data_A.shape[1]
    N_B = data_B.shape[1]
    N = N_A + N_B
    DoF = N - 6

    # Factor variables for the two replicates
    timepoints_A = numpy.array([i for i, num_reps in enumerate(num_reps_A) for j in range(num_reps)])
    timepoints_B = numpy.array([i for i, num_reps in enumerate(num_reps_B) for j in range(num_reps)])

    # Predictors, cos/sin values
    c_A = numpy.cos(timepoints_A*2*numpy.pi/len(num_reps_A))
    c_B = numpy.cos(timepoints_B*2*numpy.pi/len(num_reps_B))
    s_A = numpy.sin(timepoints_A*2*numpy.pi/len(num_reps_A))
    s_B = numpy.sin(timepoints_B*2*numpy.pi/len(num_reps_B))
    const_A = numpy.ones(c_A.shape)
    const_B = numpy.ones(c_B.shape)
    predictor_A = numpy.vstack([c_A,s_A,const_A]).T
    predictor_B = numpy.vstack([c_B,s_B,const_B]).T

    # Variances of predictor values (cos, sin)
    X_A = numpy.sum( (c_A - numpy.mean(c_A))**2 )
    Z_A = numpy.sum( (s_A - numpy.mean(s_A))**2 )
    T_A = numpy.sum( (s_A - numpy.mean(s_A))*(c_A - numpy.mean(c_A)) ) # covariance
    X_B = numpy.sum( (c_B - numpy.mean(c_B))**2 )
    Z_B = numpy.sum( (s_B - numpy.mean(s_B))**2 )
    T_B = numpy.sum( (s_B - numpy.mean(s_B))*(c_B - numpy.mean(c_B)) ) # covariance

    # Used for estimates of covariances of beta and gamma as matrix [[c22, c23], [c23, c33]]
    c22_A =  Z_A / (X_A * Z_A - T_A**2)
    c23_A = -T_A / (X_A * Z_A - T_A**2)
    c33_A =  X_A / (X_A * Z_A - T_A**2)
    c22_B =  Z_B / (X_B * Z_B - T_B**2)
    c23_B = -T_B / (X_B * Z_B - T_B**2)
    c33_B =  X_B / (X_B * Z_B - T_B**2)

    # Fitting to the model
    # y ~ beta * cos(t) + gamma * sin(t) + M + epsilon
    # solving for beta, gamma, M with residual epsilon being normally distributed

    p_amplitude = numpy.ones(num_features)
    p_phase = numpy.ones(num_features)
    for i in range(num_features):
        # For each feature, perform Least-Squares fits

        # TODO: if no missing values, can actually compute all of these at once by passing in all of data_A (or maybe data_A.T)
        x_A, resid_A, rank_A, sing_A = numpy.linalg.lstsq(predictor_A, data_A[i], rcond=None)
        x_B, resid_B, rank_B, sing_B = numpy.linalg.lstsq(predictor_B, data_B[i], rcond=None)

        # Best-fit parameters
        beta_A, gamma_A, M_A = x_A
        beta_B, gamma_B, M_B = x_B

        # Amplitudes
        amp_A = numpy.sqrt(beta_A**2 + gamma_A**2)
        amp_B = numpy.sqrt(beta_B**2 + gamma_B**2)

        # Acrophases (peak times)
        # so model will be y ~ amp * cos(t - phi_A) + M + epsilon
        phi_A = numpy.arctan2(gamma_A, beta_A)
        phi_B = numpy.arctan2(gamma_B, beta_B)

        # Unexplained variances
        # 3 DoF used by the model
        sigma_sq_A = resid_A / (N_A - 3)
        sigma_sq_B = resid_B / (N_B - 3)
        sigma = numpy.sqrt( ((N_A - 3) * resid_A + (N_B - 3) * resid_B)/DoF )

        # For estimated variances of amplitude and phase variables
        c22_phi_A = c22_A * cos(phi_A)**2 - 2*c23_A*cos(phi_A)*sin(phi_A) + c33_A*sin(phi_A)**2
        c33_phi_A = c22_A * sin(phi_A)**2 + 2*c23_A*cos(phi_A)*sin(phi_A) + c33_A*cos(phi_A)**2
        c22_phi_B = c22_B * cos(phi_B)**2 - 2*c23_B*cos(phi_B)*sin(phi_B) + c33_B*sin(phi_B)**2
        c33_phi_B = c22_B * sin(phi_B)**2 + 2*c23_B*cos(phi_B)*sin(phi_B) + c33_B*cos(phi_B)**2

        ## EQUAL VARIANCES BETWEEN DATA_A AND DATA_B case:
        # # Approximate test for equality of amplitudes
        # t_amplitude = numpy.abs(amp_A - amp_B) / (sigma * numpy.sqrt(c22_phi_A + c22_phi_B))
        # p_amplitude[i] = 2*scipy.stats.t.sf(t_amplitude, DoF)

        # # Approximate test for equality of phases
        # t_phase = numpy.abs(beta_A*gamma_B - beta_B*gamma_A) / (sigma * numpy.sqrt(amp_B**2*c33_phi_A + amp_A**2*c33_phi_B))
        # p_phase[i] = 2*scipy.stats.t.sf(t_phase, DoF)

        ## Unequal variances allowed (with approximate DoF calculated)
        # Approximate test for equality of amplitudes
        t_amplitude = numpy.abs(amp_A - amp_B) / numpy.sqrt(c22_phi_A*sigma_sq_A + c22_phi_B*sigma_sq_B)
        rho = c22_phi_B*sigma_sq_B/(c22_phi_A*sigma_sq_A)
        dof = (1 + rho)**2/(1/(N_A-3) + rho**2/(N_B-3))
        p_amplitude[i] = 2*scipy.stats.t.sf(t_amplitude, dof)

        # Approximate test for equality of amplitudes
        t_phase = numpy.abs(beta_A*gamma_B - beta_B*gamma_A) / numpy.sqrt(amp_B**2*c33_phi_A*sigma_sq_A + amp_A**2*c33_phi_B*sigma_sq_B)
        rho = (amp_A**2*c33_phi_B*sigma_sq_B) / (amp_B**2*c33_phi_A*sigma_sq_A**2)
        dof = (1 + rho)**2/(1/(N_A-3) + rho**2/(N_B-3))
        p_phase[i] = 2*scipy.stats.t.sf(t_phase, dof)

    return p_amplitude, p_phase
