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
