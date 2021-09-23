import numpy as np
import rpy2.robjects as R

from pathlib import Path
from rpy2.robjects.packages import STAP

START_PERIOD = 20
END_PERIOD = 28


def jtk(data, sample_collection_times, compute_wave_properties=False):
    with open(Path(__file__).parent / "algorithm.R") as algorithm:
        JTK = STAP(algorithm.read(), "JTK")

    JTK.initialize(R.FloatVector(sample_collection_times), minper=START_PERIOD, maxper=END_PERIOD)

    if compute_wave_properties:
        amplitude, lag, period = [], [], []
        for y in data:
            if all(np.isnan(y)):
                amplitude.append(np.nan)
                lag.append(np.nan)
                period.append(np.nan)
            else:
                wave_properties = JTK.jtkx(
                    R.FloatVector(y), compute_wave_properties=True
                )
                amplitude.append(wave_properties[3])
                lag.append(wave_properties[2])
                period.append(wave_properties[1])

        return amplitude, lag, period

    else:
        p = []
        for y in data:
            if all(np.isnan(y)):
                p.append(np.nan)
            else:
                p.append(JTK.jtkx(R.FloatVector(y))[0])

        return [p]
