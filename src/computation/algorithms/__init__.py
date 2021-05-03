import importlib

ALGORITHMS = ["cosinor", "ls", "arser"]

def compute(algorithm):
    if not algorithm in ALGORITHMS:
        raise NotImplementedError

    return importlib.import_module(f"algorithms.{algorithm}").algorithm
