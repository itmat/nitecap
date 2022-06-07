import numpy as np
import statsmodels.api as sm

from utilities import enough_timepoints, remove_missing_values


def cosinor(data, sample_collection_times, cycle_length=24):
    """
    Fit data to cosinor model with parameters x₀, x₁, x₂:

        y(t) = x₀ + x₁cos(ωt) + x₂sin(ωt),  ω=2π/T

    Germaine Cornelissen, ”Cosinor-based rhythmometry”,
    Theoretical Biology and Medical Modelling 11:16 (2014)
    """

    ω = 2 * np.pi / cycle_length
    x, p = [], []

    for y in data:
        y, t = remove_missing_values(y, sample_collection_times)

        if not enough_timepoints(t, cycle_length):
            x.append([np.nan, np.nan, np.nan])
            p.append(np.nan)
            continue

        fit = sm.OLS(
            y,
            np.array(
                [
                    np.repeat(1.0, t.size),
                    np.cos(ω * t),
                    np.sin(ω * t),
                ]
            ).T,
        ).fit()

        x.append(fit.params.tolist())
        p.append(fit.f_pvalue)

    return x, p
