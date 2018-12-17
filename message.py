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
    """ Indicates a header in HTTP-message.
    you can access via key, value 
    """

    re = r'(\S+?):(.+?)\r\n'
    def __init__(self, key=None, value=None):
        super(Header, self).__init__()
        self.key = key
        self.value = value


    @classmethod
    def load(cls, str_):
        key, value = None, None
        try:
            logger.info('Header.load({})'.format(str_))
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
        return self.key == None

    def save(self):
        return '{}:{}\r\n'.format(self.key, self.value)

class Headers(dict, util.serializable):
    def save(self):
        return str(self)

    @classmethod
    def load(cls, text):
        headers = cls()
        while True:
            header, text = Header.load(text)
            if not header.is_empty():
                headers[header.key] = header.value
            else:
                break
        return headers, text


class StatusLine(util.serializable):
    def __init__(self, version, StatusLine):
        self.version = version
        self.code = StatusLine.value
        self.reason = StatusLine.phrase

    def save(self):
        return '{} {} {}\r\n'.format(self.version, self.code, self.reason)


class ResponseBody(util.serializable):
    """docstring for ResponseBody"""
    re = r'(.*)'
    def __init__(self, str_):
        super(ResponseBody, self).__init__()
        self.data = str_

    @classmethod
    def load(cls, str_):
        return cls(str_), ''

    def save(self):
        return self.data
        

class RequestBody(util.serializable):
    """docstring for RequestBody"""
    re = r'[\r\n]*(.+?)=([^&\?]+)&?'
    def __init__(self, input_=None):
        super(RequestBody, self).__init__()
        self.data = input_ # todo: wriute error handling, input_ is not dict nor str

    @classmethod
    def load(cls, str_):

        try:
            parsed = {}
            for i in re.finditer(RequestBody.re, str_, re.MULTILINE):
                str_ = re.sub(RequestBody.re, '', str_, count=1)
                key, value = i.groups()
                parsed[key] = value

        except Exception as e:
            logger.warning(e)
            tb = sys.exc_info()[2]
            raise BadRequest().with_traceback(tb)

        logger.debug('RequestBody.load({})'.format(parsed))
        return cls(parsed), str_ # text must be '\r\n'?
        
    def save(self):
        res = []
        if isinstance(self.data, dict):
            for k, v in self.data.items():
                res.append('{}={}'.format(k, v))
     
            if res:
                res = '&'.join(res)
            else:
                res = ''
        elif isinstance(self.data, str):
            res = self.data
 
        return '\r\n' + res


class HTTPMessage(util.serializable):
    def __init__(self, start_line=None, headers={}, body=None):
        super(HTTPMessage, self).__init__()
        self.start_line = start_line
        self.headers = headers
        self.body = body

    def is_empty(self):
        return self.start_line.is_empty() \
             & len(self.headers) == 0 \
             & len(self.body) == 0

    @classmethod
    def load(cls, str_, isResponse=True):
        start_line, text = RequestLine.load(str_)

        headers, text = Headers().load(text)

        # consider to use factory pattern or method
        if isResponse:
            body, text = RequestBody.load(text)
        else:
            body, text = ResponseBody.load(text)

        return cls(start_line, headers, body), text

    def save(self):
        res = self.start_line.save() \
            + self.headers.save() \
            + self.body.save()
        return res
# TODO!!!! create Headers class