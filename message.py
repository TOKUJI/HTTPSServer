import http
import re
import sys

# private source
import util
from logger import get_logger_set
logger, log = get_logger_set('message')


class BadRequest(Exception):
    status = http.HTTPStatus.BAD_REQUEST

class NotFound(Exception):
    status = http.HTTPStatus.NOT_FOUND

class URITooLong(Exception):
    status = http.HTTPStatus.REQUEST_URI_TOO_LONG

class RequestEntityTooLarge(Exception):
    status = http.HTTPStatus.REQUEST_ENTITY_TOO_LARGE

class InternalServerError(Exception):
    status = http.HTTPStatus.INTERNAL_SERVER_ERROR

class MediaType(util.serializable):
    re = r'(\S+?)/(\S+?) ?; ?(\S+?=\S+)'
    pass

class RequestLine(util.serializable):
    re = r'(\S+) (\S+) (\S+)\r\n'

    def __init__(self, method, uri, version):
        super(RequestLine, self).__init__()
        self.method = method
        self.uri = uri
        self.version = version
        self._is_empty = False

    @classmethod
    def load(cls, str_):
        try:
            method, uri, version = re.match(RequestLine.re, str_).groups()
            text = re.sub(RequestLine.re, '', str_, count=1)
        except Exception as e:
            tb = sys.exc_info()[2]
            raise BadRequest().with_traceback(tb)
        return cls(method, uri, version), text

    def save(self):
        return '{} {} {}\r\n'.format(self.method, self.uri, self.version)

    def __repr__(self):
        return self.save()


class Header(util.serializable):
    re = r'(\S+?):(.+?)\r\n'
    def __init__(self, key=None, value=None):
        super(Header, self).__init__()
        self.key = key
        self.value = value


    @classmethod
    def load(cls, str_):
        try:
            logger.info(str_)
            m = re.match(Header.re, str_) # consider to use re.finditer
            if m:
                key, value = m.groups()
            text = re.sub(Header.re, '', str_, count=1)

        except Exception as e:
            logger.warning(e)
            tb = sys.exc_info()[2]
            raise BadRequest().with_traceback(tb)

        return cls(key, value), text

    def is_empty(self):
        return self.key != None

    def save(self):
        return '{}:{}\r\n'.format(self.key, self.value)

    def __repr__(self):
        return self.save()


class StatusLine(util.serializable):
    def __init__(self, version, StatusLine):
        self.version = version
        self.code = StatusLine.value
        self.reason = StatusLine.phrase

    def save(self):
        return '{} {} {}\r\n'.format(self.version, self.code, self.reason)


class HTTPMessage(util.serializable):
    def __init__(self, start_line=None, headers={}, message=None):
        super(HTTPMessage, self).__init__()
        self.start_line = start_line
        self.headers = headers
        self.message = message

    def is_empty(self):
        return self.start_line.is_empty() \
             & len(self.headers) == 0 \
             & len(self.message) == 0

    @classmethod
    def load(cls, str_):
        start_line, text = RequestLine.load(str_)

        headers = {}
        while True:
            header, text = Header.load(text)
            if header.is_empty():
                break
            headers[header.key] = header.value

        message = re.sub('^\r\n', '', text, count=1)

        return cls(start_line, headers, message), ''

    def save(self):
        res = self.start_line.save() \
            + ''.join([x.save() for x in self.headers]) \
            + '\r\n' \
            + self.message if self.message else ''
        return res

    def __repr__(self):
        return self.save()
