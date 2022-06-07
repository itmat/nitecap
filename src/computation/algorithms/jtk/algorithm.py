import numpy as np

from pathlib import Path

from rpy2.robjects import numpy2ri
from rpy2.robjects.packages import STAP

from utilities import enough_timepoints, remove_missing_values

numpy2ri.activate()

START_PERIOD = 20
END_PERIOD = 28


def jtk(data, sample_collection_times, compute_wave_properties=False):
    with open(Path(__file__).parent / "algorithm.R") as algorithm:
        JTK = STAP(algorithm.read(), "JTK")

    JTK.initialize(sample_collection_times, minper=START_PERIOD, maxper=END_PERIOD)

    p, period, lag, amplitude = [], [], [], []

    for y in data:
        _, t = remove_missing_values(y, sample_collection_times)

        if not enough_timepoints(t, (START_PERIOD + END_PERIOD) // 2):
            for property in (p, period, lag, amplitude):
                property.append(np.nan)
        else:
            wave_properties = JTK.jtkx(
                y, compute_wave_properties=compute_wave_properties
            )
            for property, value in zip((p, period, lag, amplitude), wave_properties):
                property.append(value)

    if compute_wave_properties:
        return period, lag, amplitude
    else:
        return [p]
