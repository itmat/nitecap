import rpy2.robjects as R

from pathlib import Path
from rpy2.robjects.packages import STAP

START_PERIOD = 20
END_PERIOD = 28


def jtk(data, timepoints):
    with open(Path(__file__).parent / "algorithm.R") as algorithm:
        JTK = STAP(algorithm.read(), "JTK")

    JTK.initialize(R.FloatVector(timepoints), minper=START_PERIOD, maxper=END_PERIOD)

    p = []
    for y in data:
        p.append(JTK.jtkx(R.FloatVector(y))[0])

    return [p]
