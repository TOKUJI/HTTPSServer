from functools import wraps
from logging import getLogger


def get_logger(name):
    return getLogger('simpleLedger').getChild(name)

def get_log_decorator(name):
    logger = get_logger(name)

    def _log(fn):
        @wraps(fn)
        def wrapper(*args, **kwds):
            logger.debug('{}({}, {})'.format(fn.__name__, args, kwds))
            res = fn(*args, **kwds)
            return res
        return wrapper
    return _log
