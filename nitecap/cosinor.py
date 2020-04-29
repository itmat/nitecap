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

    X, *_ = np.linalg.lstsq(A, Y)

    Ŷ = X[0] + np.outer(X[1], np.cos(ω*t)).T + np.outer(X[2], np.sin(ω*t)).T
    Ȳ = np.mean(Y, axis=0)

    MSS = np.linalg.norm(Ŷ-Ȳ, axis=0)**2
    RSS = np.linalg.norm(Ŷ-Y, axis=0)**2
    F = (MSS/2) / (RSS/(N-3))
    p = 1.0 - f.cdf(F, 2, N-3)

    return X, p