import numpy as np
from scipy.stats import f_oneway

from collections import defaultdict


def remove_missing_values(y, sample_collection_times):
    indices_of_finite_values_of_y = np.isfinite(y)
    return (
        y[indices_of_finite_values_of_y],
        sample_collection_times[indices_of_finite_values_of_y],
    )


def one_way_anova(data, sample_collection_times, cycle_length=24):
    p = []
    for y in data:
        y, t = remove_missing_values(y, sample_collection_times)

        groups = defaultdict(list)
        for t_mod_cycle_length, value in zip(t % cycle_length, y):
            groups[t_mod_cycle_length].append(value)

        groups = groups.values()

        if all(len(group) == 1 for group in groups) or len(groups) < 2:
            p.append(np.nan)
        else:
            p.append(f_oneway(*groups)[1])

    return [p]
