import numpy as np
import statsmodels.api as sm


def cosinor(data, timepoints, cycle_length=24):
    """
    Fit data to cosinor model with parameters x₀, x₁, x₂:

        y(t) = x₀ + x₁cos(ωt) + x₂sin(ωt),  ω=2π/T

    Germaine Cornelissen, ”Cosinor-based rhythmometry”,
    Theoretical Biology and Medical Modelling 11:16 (2014)
    """

    ω = 2 * np.pi / cycle_length
    x, p = [], []

    for y in data:
        fit = sm.OLS(
            y,
            np.array(
                [
                    np.repeat(1.0, timepoints.size),
                    np.cos(ω * timepoints),
                    np.sin(ω * timepoints),
                ]
            ).T,
            missing="drop",
        ).fit()

        x.append(fit.params.tolist())
        p.append(fit.f_pvalue if not np.isnan(fit.f_pvalue) else 1.0)

    return x, p
