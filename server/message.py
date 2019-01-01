import http
import re
import sys
import io
from http.cookies import SimpleCookie
from collections import defaultdict

# private source
from .util import serializable, MessageType, HeaderFields
from .logger import get_logger_set
logger, log = get_logger_set('message')

class BaseHTTPError(Exception):
    def get_message(self):
        if not self.status:
            raise NotImplementedException()

        return '{} {}'.format(self.status.value, self.status.phrase)

class BadRequest(BaseHTTPError):
    status = http.HTTPStatus.BAD_REQUEST

class UnauthorizedError(BaseHTTPError):
    status = http.HTTPStatus.UNAUTHORIZED
        
class NotFound(BaseHTTPError):
    status = http.HTTPStatus.NOT_FOUND

class URITooLong(BaseHTTPError):
    status = http.HTTPStatus.REQUEST_URI_TOO_LONG

class RequestEntityTooLarge(BaseHTTPError):
    status = http.HTTPStatus.REQUEST_ENTITY_TOO_LARGE

class InternalServerError(BaseHTTPError):
    status = http.HTTPStatus.INTERNAL_SERVER_ERROR

class MethodNotAllowed(BaseHTTPError):
    status = http.HTTPStatus.METHOD_NOT_ALLOWED

class NotImplementedError(BaseHTTPError):
    status = http.HTTPStatus.NOT_IMPLEMENTED

class MediaType(serializable):
    re = r'(\S+?)/(\S+?) ?; ?(\S+?=\S+)'


class RequestLine(serializable):
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
        except Exception as e:
            tb = sys.exc_info()[2]
            raise BadRequest().with_traceback(tb)
        return cls(method, uri, version)

    def save(self):
        return '{} {} {}\r\n'.format(self.method, self.uri, self.version)

    def __repr__(self):
        return self.save()


class Header(serializable):
    """ Indicates a header in HTTP-message.
    you can access via key, value 
    """

    re = r'(\S+?): ?(.+)'
    def __init__(self, key=None, value=None):
        super(Header, self).__init__()
        self.key = key
        self.value = value


    @classmethod
    @log
    def load(cls, str_):
        key, value = None, None
        try:
            m = re.match(Header.re, str_) # consider to use re.finditer
            key, value = m.groups()

        except Exception as e:
            logger.warning(e)
            raise BadRequest().with_traceback(sys.exc_info()[2])

        return cls(key, value)

    def is_empty(self):
        return self.key == None

    def save(self):
        return '{}: {}\r\n'.format(self.key, self.value)


class Headers(dict, serializable):
    def __init__(self, *, headers=[], cookie=SimpleCookie(), **kwds, ):
        super(dict, self).__init__()
        self.cookie = cookie
        [self.set_header(header) for header in headers]

    def set_cookie(self, key, value):
        self.cookie[key] = value

    def get_cookie(self, key):
        return self.cookie[key]

    def has_message_body(self):
        if HeaderFields.CONTENT_TYPE.value in self.keys() \
            or HeaderFields.TRANSFER_ENCODING.value in self.keys():
            return True
        return False

    def save(self):
        res = [Header(k, v).save() for k, v in self.items()]
        text = ''.join(res)

        if self.cookie:
            text += self.cookie.output() + '\r\n'

        return text + '\r\n'

    def set_header(self, header):
        if header.key == 'Cookie':
            self.cookie.load(header.value)
        else:
            self[header.key] = header.value

    @classmethod
    def load(cls, text):
        headers = cls()

        lines = text.split('\r\n')
        heads = [Header.load(line) for line in lines if line]

        for header in heads:
            headers.set_header(header)

        return headers


class StatusLine(serializable):
    def __init__(self, version, StatusLine):
        self.version = version
        self.code = StatusLine.value
        self.reason = StatusLine.phrase

    def save(self):
        return '{} {} {}\r\n'.format(self.version, self.code, self.reason)


class ResponseBody(serializable):
    """docstring for ResponseBody"""
    re = r'(.*)'
    def __init__(self, str_):
        super(ResponseBody, self).__init__()
        self.data = str_

    @classmethod
    def load(cls, str_):
        return cls(str_)

    def save(self):
        return self.data
        

class RequestBody(serializable):
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
        return cls(parsed)
        
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

class RequestBodyJson(serializable):
    def __init__(self, data):
        super(RequestBodyJson, self).__init__()
        self.data = data

    @classmethod
    def load(cls, text):
        import json
        try:
            data = json.loads(text)
        except Exception as e:
            logger.warning(e)
            raise e
        return cls(data)

    def save(self):
        return '\r\n' + json.dumps(self.data)


class HTTPMessage(serializable):
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
    def load(cls, str_, message_type=MessageType.REQUEST):
        try:
            stream = io.StringIO(str_)
            start_line = RequestLine.load(stream.readline())

            x = stream.read().split('\r\n\r\n')
            headers = Headers.load(x[0])

            body = None

            # TODO: implement to follow transfer-coding
            if HeaderFields.TRANSFER_ENCODING in headers:
                raise NotImplementedError()
            # TODO: implement to handle Content-Length header
            # TODO: implement to handle Connection header
            
            if headers.has_message_body():
                body = _bodyClass[(message_type,
                                   headers[HeaderFields.CONTENT_TYPE.value])
                                 ].load(x[1])

        except Exception as e:
            logger.error(e)
            raise BadRequest()

        return cls(start_line, headers, body)

    def save(self):
        res = self.start_line.save() + self.headers.save()

        if self.body:
            res += self.body.save()

        return res

_bodyClass = {
    (MessageType.REQUEST, None): RequestBody,
    (MessageType.REQUEST, 'application/json'): RequestBodyJson,
    (MessageType.REQUEST, 'application/x-www-form-urlencoded'): RequestBody,
    (MessageType.RESPONSE, None): ResponseBody,
}