from functools import wraps
from inspect import signature, iscoroutine
import asyncio
import ssl
import sys
from http import HTTPStatus
from datetime import timezone, datetime
from enum import Enum, auto
# from urllib.parse import urlparse, parse_qs

# private library
# from .message import *
from . import message
from . import util
from .rsock import create_socket
from .frame import FrameBase, FrameTypes, SettingFrame, HeadersFlags, DataFlags

from .logger import get_logger_set
logger, log = get_logger_set('server')


class HandlerTypes(Enum):
    HTTP1_1 = auto()
    HTTP2 = auto()
        
class HandlerBase(object):
    def __init__(self, router, reader, writer):
        self.router = router
        self.reader = reader
        self.writer = writer

    async def handle_request(self, path):
        """ Handles HTTP request method. Call an appropriate function from path and method."""
        raise NotImplementedException()


    @classmethod
    def find_handler(cls, handler_type):
        handlers = {klass.handler_type(): klass for klass in cls.__subclasses__()}
        return handlers[handler_type]
    
    @staticmethod
    def hander_type():
        raise NotImplementedException('Handler must implement handler_type() function')


class HTTP1_1Handler(HandlerBase):
    def __init__(self, router, reader, writer):
        super(HTTP1_1Handler, self).__init__(router, reader, writer)

    @staticmethod
    def handler_type():
        return HandlerTypes.HTTP1_1

    @log
    async def parse(self, data):
        """ Parse HTTP/1.1 request """
        text = data.decode('utf-8')
        request = message.HTTPMessage.load(text)
        return request

    def make_headers(self):
        x = [message.Header('Date', datetime.now(tz=timezone.utc).strftime(util.IMFFixdate)),
             message.Header('Server', 'SimpleServer'),
             message.Header('Content-Type', 'text/html;charset=utf-8'),
            ]
        return message.Headers(headers=x)


    def write_error(self, exception, writer):
        status = message.StatusLine('HTTP/1.1', exception.status)
        headers = self.make_headers()
        msg = exception.get_message()
        logger.debug(msg)
        body = message.ResponseBody(msg)
        result = message.HTTPMessage(status, headers, body).save()
        writer.write(result.encode('utf-8'))


    @log
    async def handle_request(self, request):
        """ Handle request and write the result to writer """
        try:
            fn, methods = self.router.find(request.start_line.uri)
            if request.start_line.method not in methods:
                raise message.MethodNotAllowed()

            if request.body:
                response = await self.call_with_args(fn, request)
            else:
                response = await self.call_with_args(fn, None)

            logger.debug(response)
            logger.debug(response.save())

            if isinstance(response, str):
                response = self.make_response(response)

            # append cookie
            headers = self.make_headers()
            for k, v in request.headers.cookie.items():
                if k not in headers.cookie:
                    headers.set_cookie(k, v)

            # append Content-Length header
            length = len(response.body.save().encode('utf-8'))
            headers.set_header(message.Header('Content-Length', length))

            response.headers = headers

            self.writer.write(response.save().encode('utf-8'))

        except KeyError as e:
            logger.warning(e)
            self.write_error(message.NotFound().with_traceback(sys.exc_info()[2]), self.writer)
        except TypeError as e:
            logger.warning(e)
            e = message.InternalServerError().with_traceback(sys.exc_info()[2])
            self.write_error(e, self.writer)
        except message.BaseHTTPError as e:
            e = e.with_traceback(sys.exc_info()[2])
            logger.warning(e)
            self.write_error(e, self.writer)

        await self.writer.drain()

    async def call_with_args(self, fn, request):
        """ If request body has some key-value pair and fn requires
        the same arguments, this function call the fn with arguments
        supplied in the body.
        """

        sig = signature(fn)
        # delete undeclared parameters
        if request:
            params = {k:v for k, v in request.body.data.items() if k in sig.parameters}
        else:
            params = {}

        if 'request' in sig.parameters.keys():
            bn = sig.bind_partial(request=request, **params)
        else:
            bn = sig.bind_partial(**params)

        res = fn(*bn.args, **bn.kwargs)

        if iscoroutine(res):
            return await res
        else:
            return res

class HTTP2Handler(HandlerBase):
    """docstring for HTTP2Server"""
    def __init__(self, router, reader, writer):
        super(HTTP2Handler, self).__init__(router, reader, writer)
        self.client_stream_window_size = {}

    async def run(self):
        frame = await self.parse_stream()
        my_settings = FrameBase.create(FrameTypes.SETTINGS.value, 0x0, frame.stream_identifier)
        await self.send_frame(my_settings)
        await self.handle_frame(frame)


        while True:
            frame = await self.parse_stream()
            if not frame:
                break
            await self.handle_frame(frame)

    async def parse_stream(self):
        data = await self.reader.read(9)
        if len(data) != 9:
            return
        payload = int.from_bytes(data[:3], 'big', signed=False)
        data += await self.reader.read(payload)
        return FrameBase.load(data)
        
    async def handle_request(self, header):
        fn, methods = self.router.find(header[':path'])
        if header[':method'] not in methods:
            raise message.MethodNotAllowed()

        reply_header = FrameBase.create(FrameTypes.HEADERS.value,
                                        HeadersFlags.END_HEADERS.value,
                                        header.stream_identifier)
        reply_header[':status'] = HTTPStatus.OK.value
        await self.send_frame(reply_header)

        res = await fn()
        res = res.encode('utf-8')
        reply_data = FrameBase.create(FrameTypes.DATA.value,
                                      DataFlags.END_STREAM.value,
                                      header.stream_identifier,
                                      res)
        await self.send_frame(reply_data)

    async def handle_frame(self, frame):
        if frame.FrameType() == FrameTypes.HEADERS:
            await self.handle_request(frame)

        elif frame.FrameType() == FrameTypes.SETTINGS:
            if frame.flags == 0x0:
                await self.send_frame(FrameBase.create(FrameTypes.SETTINGS.value, 0x1, frame.stream_identifier))
                if frame.initial_window_size:
                    self.initial_window_size = frame.initial_window_size

            elif frame.flags == 0x1:
                logger.debug('Got ACK')

        elif frame.FrameType() == FrameTypes.WINDOW_UPDATE:
            if frame.stream_identifier == 0:
                self.client_window_size = frame.window_size
            else:
                self.client_stream_window_size[frame.stream_identifier] = frame.window_size

    async def send_frame(self, frame):
        self.writer.write(frame.save())
        await self.writer.drain()

    @staticmethod
    def handler_type():
        return HandlerTypes.HTTP2


class MyHTTPServer(object):
    """ HTTP Server class. When ssl_context or certfile is set,
    this server runs as a HTTPS server.
    """
    def __init__(self, 
                 router = util.RouteRecord(),
                 # handlers = HTTP1_1Handler(self._route, request, writer),
                 *, ssl_context =None, certfile=None, keyfile=None, password=None, **kwds):

        # Create TLS context
        if ssl_context and certfile:
            raise TypeError('SSLContext and certfile must not be set at the same time')

        if ssl_context:
            self.ssl = ssl_context
        elif certfile:
            context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
            context.set_alpn_protocols(['HTTP/1.1', 'h2']) # to enable HTTP/2, add 'h2'
            context.load_cert_chain('server.crt', keyfile='server.key')
            context.options |= ssl.OP_NO_TLSv1 | ssl.OP_NO_TLSv1_1
            context.options |= ssl.OP_NO_COMPRESSION
            self.ssl = context

        self._route = router

    def make_response(self, text):
        status = message.StatusLine('HTTP/1.1', HTTPStatus.OK)
        body = message.ResponseBody.load(text)
        return message.HTTPMessage(start_line=status, body=body)


    async def client_connected_cb(self, reader, writer):
        try:
            request_data = await reader.read(24)
            if request_data == util.HTTP2:
                logger.info('HTTP/2 connection is requested.')

                http2 = HandlerBase.find_handler(HandlerTypes.HTTP2)(self._route, reader, writer)
                await http2.run()

            else:
                if reader.at_eof():
                    raise message.RequestEntityTooLarge().with_traceback(sys.exc_info()[2])

                handler = HandlerBase.find_handler(HandlerTypes.HTTP1_1)(self._route, reader, writer)
                request = await handler.parse(request_data)
                response = await handler.handle_request(request)

        except Exception as e:
            self.write_error(e, writer)

        finally:
            writer.close()

    async def run(self, port=80):
        rsock_ = create_socket((None, port))
        if self.ssl:
            self.socket = self.ssl.wrap_socket(rsock_, server_side=True)
        await asyncio.start_server(self.client_connected_cb, sock=self.socket)

    def route(self, method='GET', path='/'):
        return self._route.route(method=method, path=path)

