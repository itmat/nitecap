import numpy as np
from scipy.optimize import least_squares
from scipy.stats import f

def cosinor(x, t, ω=2*np.pi/24):
    # t is in hours
    return x[0] + x[1]*np.cos(ω*t) + x[2]*np.sin(ω*t)

def residuals(x, t, y):
    return cosinor(x, t) - y

def fit(data, N_DAYS):
    N_TIMEPOINTS, N_REPS, N_GENES = data.shape

    coefficient = 24*N_DAYS/N_TIMEPOINTS    # makes the unit of t hours
    t = np.repeat(np.arange(N_TIMEPOINTS)*coefficient, N_REPS)

    Y = data.reshape( (N_TIMEPOINTS * N_REPS, N_GENES) )
    
    X = np.empty((N_GENES, 3))
    p = np.empty((N_GENES, ))

    N = t.size
    for gene in range(N_GENES):
        y = Y[:,gene]
        mean = np.sum(y)/N
    
        x = least_squares(residuals, [mean, 0.0, 0.0], args=(t, y)).x
        X[gene,:] = x
    
        MSS = np.sum((cosinor(x, t) - mean)**2)
        RSS = np.sum((y - cosinor(x, t))**2)
        F = (MSS/2) / (RSS/(N-3))
        p[gene] = 1.0 - f.cdf(F, 2, N-3)
    
    return X, p