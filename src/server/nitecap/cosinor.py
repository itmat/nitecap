import numpy as np
from scipy.stats import f

def fit(data, timepoints, timepoints_per_cycle, T=24):
    '''
    Fit data to cosinor model with parameters x₀, x₁, x₂:

        Y(t) = x₀ + x₁cos(ωt) + x₂sin(ωt),  ω=2π/T

    Germaine Cornelissen, ”Cosinor-based rhythmometry”,
    Theoretical Biology and Medical Modelling 11:16 (2014)
    '''

    N_FEATURES, N_SAMPLES = data.shape

    Δt = T/timepoints_per_cycle     # duration between timepoints (in hours)
    t = timepoints

    Y = data.T

    N = t.size
    ω = 2*np.pi/T
    A = np.array([ np.repeat(1.0, N),
                   np.cos(ω*t),
                   np.sin(ω*t) ]).T

    # Check for nans
    finite_mask = np.isfinite(Y)
    contains_nans = not np.all(finite_mask)

    # Regress each row separately
    # While slower than doing the vectorized approach with Numpy,
    # this handles variable missing data between each row, which cannot
    # easily be handled otherwise
    cosinor_p = np.empty(N_FEATURES)
    cosinor_X = np.empty((3, N_FEATURES))
    for i in range(N_FEATURES):
        row = Y[:,i]
        row_A = A
        row_t = t

        if contains_nans:
            # Remove non-nans
            row = row[finite_mask[:,i]]
            row_A = A[finite_mask[:,i]]
            row_t = t[finite_mask[:,i]]

        if len(row) < 3:
            # Too little data to be able to fit at all
            p = float("NaN")
            X = float("NaN")
        else:

            # Perform the regression on the row's data
            X, *_ = np.linalg.lstsq(row_A, row, rcond=None)
            Ŷ = (row_A @ X)
            Ȳ = np.mean(row, axis=0)

            # Compute p-value
            N=len(row)
            MSS = np.linalg.norm(Ŷ-Ȳ, axis=0)**2
            RSS = np.linalg.norm(Ŷ-row, axis=0)**2
            F = (MSS/2) / (RSS/(N-3))
            p = 1.0 - f.cdf(F, 2, N-3)

        cosinor_p[i] = p
        cosinor_X[:,i] = X

    return cosinor_X, cosinor_p
