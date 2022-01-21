import numpy as np
import rpy2.robjects as R

from pathlib import Path
from rpy2.robjects.packages import STAP

START_PERIOD = 20
END_PERIOD = 28


def jtk(data, sample_collection_times, compute_wave_properties=False):
    with open(Path(__file__).parent / "algorithm.R") as algorithm:
        JTK = STAP(algorithm.read(), "JTK")

    JTK.initialize(
        R.FloatVector(sample_collection_times), minper=START_PERIOD, maxper=END_PERIOD
    )

    p, period, lag, amplitude = [], [], [], []

    for y in data:
        if all(np.isnan(y)):
            for property in (p, period, lag, amplitude):
                property.append(np.nan)
        else:
            wave_properties = JTK.jtkx(
                R.FloatVector(y), compute_wave_properties=compute_wave_properties
            )
            for property, value in zip((p, period, lag, amplitude), wave_properties):
                property.append(value)

    if compute_wave_properties:
        return period, lag, amplitude
    else:
        return [p]
