import numpy as np
from numpy import exp, sin, cos, arctan2

MINIMUM_PERIOD = 20
MAXIMUM_PERIOD = 28


def remove_missing_values(y, timepoints):
    indices_of_finite_values_of_y = np.isfinite(y)
    return y[indices_of_finite_values_of_y], timepoints[indices_of_finite_values_of_y]


def ls(data, timepoints):
    test_frequencies = np.linspace(
        1 / MAXIMUM_PERIOD, 1 / MINIMUM_PERIOD, 4 * timepoints.size
    )

    p = []
    for y in data:
        y, t = remove_missing_values(y, timepoints)

        if np.var(y) == 0 or t.size == 0:
            p.append(1.0)  # check if this makes sense
            continue

        number_of_independent_frequencies = horne_baliunas(t.size)

        r = y - np.mean(y)

        spectral_power_density = np.empty(test_frequencies.size)
        for i, test_frequency in enumerate(test_frequencies):
            ω = 2 * np.pi * test_frequency
            τ = np.arctan2(np.sum(sin(2 * ω * t)), np.sum(cos(2 * ω * t))) / (2 * ω)

            Δ = ω * (t - τ)
            spectral_power_density[i] = (
                np.sum(r * cos(Δ)) ** 2 / np.sum(cos(Δ) ** 2)
            ) + (np.sum(r * sin(Δ)) ** 2 / np.sum(sin(Δ) ** 2))

        spectral_power_density /= 2 * np.var(y, ddof=1)

        peak_index = np.argmax(spectral_power_density)
        probabilities = (
            1 - (1 - exp(-spectral_power_density)) ** number_of_independent_frequencies
        )
        p.append(probabilities[peak_index])

    return [p]


def horne_baliunas(n):
    return max(1, int(-6.362 + 1.193 * n + 0.00098 * n ** 2))
