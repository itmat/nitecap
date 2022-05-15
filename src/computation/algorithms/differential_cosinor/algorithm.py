import numpy
import scipy

import statsmodels.api as sm

from numpy import cos, sin


def cosinor_analysis(timepoints_A, data_A, timepoints_B, data_B, timepoints_per_cycle):
    '''
    Perform tests using a Cosinor (sinusoidal least-squares fit) method.

    `timepoints_A` is a list of integers indicating timepoint of each column of data_A
    `data_A` is a numpy array of shape (num_features, num_samples)
            containing the values of the condition A
    `timepoints_B` is a list of integers indicating timepoint of each column of data_B
    `data_B` is a numpy array of shape (num_features, num_samples)
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

    assert len(timepoints_A) == data_A.shape[1]
    assert len(timepoints_B) == data_B.shape[1]
    assert data_A.shape[0] == data_B.shape[0]
    num_features = data_A.shape[0]
    timepoints_A = numpy.array(timepoints_A)
    timepoints_B = numpy.array(timepoints_B)

    # Predictors, cos/sin values
    c_A = numpy.cos(timepoints_A*2*numpy.pi/timepoints_per_cycle)
    c_B = numpy.cos(timepoints_B*2*numpy.pi/timepoints_per_cycle)
    s_A = numpy.sin(timepoints_A*2*numpy.pi/timepoints_per_cycle)
    s_B = numpy.sin(timepoints_B*2*numpy.pi/timepoints_per_cycle)
    const_A = numpy.ones(c_A.shape)
    const_B = numpy.ones(c_B.shape)
    predictor_A = numpy.vstack([c_A,s_A,const_A]).T
    predictor_B = numpy.vstack([c_B,s_B,const_B]).T

    # Variances of predictor values (cos, sin)
    # TODO: do these depend upon NaNs?
    # i.e. we're masking out some timepoints, effectively, so the variances could change?
    # It's unclear to me...
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
        # Number of samples in each dataset
        # after dropping NaNs
        N_A = numpy.isfinite(data_A[i]).sum()
        N_B = numpy.isfinite(data_B[i]).sum()
        N = N_A + N_B
        DoF = N - 6

        if DoF < 1:
            # Skip row - too many missing values
            p_amplitude[i] = float("NaN")
            p_phase[i] = float("NaN")
            continue

        # For each feature, perform Least-Squares fits

        res_A = sm.OLS(data_A[i], predictor_A, missing='drop').fit()
        res_B = sm.OLS(data_B[i], predictor_B, missing='drop').fit()
        x_A = res_A.params
        resid_A = (res_A.resid**2).sum()
        x_B = res_B.params
        resid_B = (res_B.resid**2).sum()

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

    return p_amplitude[0], p_phase[0]


def differential_cosinor(data, sample_collection_times, cycle_length=24):
    
    groups = []
    
    for collection_times in sample_collection_times:
        timepoints = sorted(set(collection_times))
        Δt = float(timepoints[1] - timepoints[0])

        groups.append(((collection_times % cycle_length) / Δt).astype(int))

    p_amplitude = []
    p_phase = []

    for data_A, data_B in data:
        amplitude_p_value, phase_p_value = cosinor_analysis(
            groups[0], numpy.array([data_A]),
            groups[1], numpy.array([data_B]),
            timepoints_per_cycle=int(cycle_length / Δt),
        )

        p_amplitude.append(amplitude_p_value)
        p_phase.append(phase_p_value)

    return p_amplitude, p_phase
