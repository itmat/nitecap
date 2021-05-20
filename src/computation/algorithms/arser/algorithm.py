import numpy as np
import rpy2.robjects as R
import statsmodels.api as sm

from itertools import chain
from scipy.signal import argrelextrema, detrend, savgol_filter

START_PERIOD = 20
DEFAULT_PERIOD = 24
END_PERIOD = 28

NUMBER_OF_FREQUENCIES_AT_WHICH_TO_ESTIMATE_THE_SPECTRAL_DENSITY = 500

ε = 1e-15

spec_ar = R.r["spec.ar"]


def valid_input(y, timepoints):
    # No missing values
    if any(np.isnan(y)):
        return False

    # Only one replicate per timepoint
    if len(timepoints) != len(set(timepoints)):
        return False

    # Evenly spaced time series
    Δt = timepoints[1] - timepoints[0]
    for k, t in enumerate(timepoints):
        if t != timepoints[0] + k * Δt:
            return False

    return True


def arser(data, timepoints):
    autoregressive_model_parameters_estimation_methods = ["yule-walker", "mle", "burg"]

    p = []
    for y in data:
        if not valid_input(y, timepoints):
            p.append(np.nan)
            continue

        y = detrend(y, type="linear")

        if np.var(y) < ε:
            p.append(1.0)
            continue

        models = []
        for smoothing in [True, False]:
            for method in autoregressive_model_parameters_estimation_methods:
                cycling_periods = [
                    period
                    for period in estimate_cycling_periods(
                        y, timepoints, method, smoothing
                    )
                    if START_PERIOD <= period <= END_PERIOD
                ]

                if not cycling_periods:
                    cycling_periods = [DEFAULT_PERIOD]

                x = np.concatenate(
                    (
                        [np.cos(2 * np.pi / T * timepoints) for T in cycling_periods],
                        [np.sin(2 * np.pi / T * timepoints) for T in cycling_periods],
                    )
                ).T

                models.append(sm.OLS(y, sm.add_constant(x)).fit())

        # Select models by AIC
        best_model = min(models, key=lambda model: model.aic)
        p.append(best_model.f_pvalue)

    return [p]


def estimate_cycling_periods(y, timepoints, parameters_estimation_method, smoothing):
    Δt = timepoints[1] - timepoints[0]
    autoregressive_model_order = int(24 // Δt)
    if autoregressive_model_order == timepoints.size:
        autoregressive_model_order = timepoints.size // 2

    if smoothing:
        try:
            y = savgol_filter(y, window_length=11, polyorder=4)
        except:
            y = savgol_filter(y, window_length=5, polyorder=2)

    maximum_entropy_spectral_density_estimate = spec_ar(
        R.FloatVector(y),
        method=parameters_estimation_method,
        order=autoregressive_model_order,
        n_freq=NUMBER_OF_FREQUENCIES_AT_WHICH_TO_ESTIMATE_THE_SPECTRAL_DENSITY,
        plot=False,
    )

    frequencies = np.array(maximum_entropy_spectral_density_estimate.rx2("freq"))
    spectral_density = np.array(
        maximum_entropy_spectral_density_estimate.rx2("spec")
    ).reshape(NUMBER_OF_FREQUENCIES_AT_WHICH_TO_ESTIMATE_THE_SPECTRAL_DENSITY)

    indices_of_local_maxima_of_spectral_density = argrelextrema(
        spectral_density, np.greater
    )[0]

    sorted_by_spectral_density_values = spectral_density[
        indices_of_local_maxima_of_spectral_density
    ].argsort()[::-1]

    periods = Δt / (
        frequencies[
            indices_of_local_maxima_of_spectral_density[
                sorted_by_spectral_density_values
            ]
        ]
    )
    return periods
