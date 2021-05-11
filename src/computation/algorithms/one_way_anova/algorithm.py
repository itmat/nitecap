import numpy as np
from scipy.stats import f_oneway

from collections import defaultdict


def remove_missing_values(y, timepoints):
    indices_of_finite_values_of_y = np.isfinite(y)
    return y[indices_of_finite_values_of_y], timepoints[indices_of_finite_values_of_y]


def one_way_anova(data, timepoints, timepoints_per_cycle=6):
    if timepoints.size <= timepoints_per_cycle:
        raise ValueError("Cannot perform ANOVA on datasets without any replicates")

    p = []
    for y in data:
        y, t = remove_missing_values(y, timepoints)

        groups = defaultdict(list)
        for t_mod_cycle_length, value in zip(t % timepoints_per_cycle, y):
            groups[t_mod_cycle_length].append(value)

        groups = groups.values()

        if len(groups) < 2:
            p.append(np.nan)
        else:
            p.append(f_oneway(*groups)[1])

    return [p]
