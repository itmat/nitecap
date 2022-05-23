import importlib

ALGORITHMS = ["cosinor", "differential_cosinor", "ls", "arser", "jtk", "one_way_anova", "two_way_anova", "rain", "upside"]
COMPARISON_ALGORITHMS = ["differential_cosinor", "two_way_anova", "upside"]

def compute(algorithm):
    if not algorithm in ALGORITHMS:
        raise NotImplementedError

    return importlib.import_module(f"algorithms.{algorithm}").algorithm
