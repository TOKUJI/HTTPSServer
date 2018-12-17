class serializable(object):
    """ This is ABC of util.serializable classes. Any derived class of this class
    should implement save and load method.
    """
    re = r''

    def __init__(self):
        self._is_empty = True

    def is_empty(self):
        return self._is_empty

    def save(self):
        return NotImplementedError('serializable.save()')

    @classmethod
    def load(cls, str_): # must return a pair (serializable, remaining_text)
        return NotImplementedError('serializable.load()')

import datetime
# RFC 5322 Date and Time specification
IMFFixdate = '%a, %d %b %Y %H:%M:%S %Z'


import re

URI = r'/?[0-9a-zA-Z]*?/?'

# http://taichino.com/programming/1538
from collections import UserDict
class RouteRecord(UserDict):
    """docstring for RouteRecord"""
    def __init__(self, *args, **kwds):
        super(RouteRecord, self).__init__(*args, **kwds)
        self.regex_ = {}

    def __setitem__(self, key, value):
        if isinstance(key, re.Pattern):
            self.regex_[key] = value
        else:
            self.data[key] = value
            if key[-1] != '$':
                key = key + '$'
            self.regex_[re.compile(key)] = value

    def __getitem__(self, key):
        try:
            return self.data[key]
        except:
            for k, v in self.regex_.items():
                if k.match(key):
                    return v
            raise KeyError('{} is not found'.format(key))
