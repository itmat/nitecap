import numpy as np
from scipy.stats import f

def fit(data, N_DAYS, T=24):    # T is period (in hours)
    '''
    Fit data to cosinor model with parameters x₀, x₁, x₂:

        Y(t) = x₀ + x₁cos(ωt) + x₂sin(ωt),  ω=2π/T

    Germaine Cornelissen, ”Cosinor-based rhythmometry”,
    Theoretical Biology and Medical Modelling 11:16 (2014)
    '''

    N_TIMEPOINTS, N_REPS, N_GENES = data.shape

    Δt = 24*N_DAYS/N_TIMEPOINTS     # duration between timepoints (in hours)
    t = np.repeat([k*Δt for k in range(N_TIMEPOINTS)], N_REPS)

    Y = data.reshape((N_TIMEPOINTS * N_REPS, N_GENES))

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
    cosinor_p = np.empty(N_GENES)
    cosinor_X = np.empty((3, N_GENES))
    for i in range(N_GENES):
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
            X, *_ = np.linalg.lstsq(row_A, row)
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
