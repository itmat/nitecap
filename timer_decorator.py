import time
from functools import wraps
from flask import current_app

def timeit(func):
    @wraps(func)
    def decorated_function(*args, **kwargs):
        ts = time.time()
        try:
            return func(*args, **kwargs)
        finally:
            te = time.time()
            current_app.logger.debug(f"{func.__name__} - {(te - ts) * 1000} msec")
    return decorated_function