from functools import wraps
from inspect import signature, iscoroutine
import asyncio
import ssl
import sys
from http import HTTPStatus
from datetime import timezone, datetime
# from urllib.parse import urlparse, parse_qs

# private library
# from .message import *
from . import message
from . import util
from .rsock import create_socket
from .frame import FrameBase, FrameTypes, SettingFrame

from .logger import get_logger_set
logger, log = get_logger_set('server')


class MyHTTPServer(object):
    def __init__(self, ssl_context =None,
                 router = util.RouteRecord(),
                 *, certfile=None, keyfile=None, password=None, **kwds):
        """ HTTP Server class. When ssl_context or certfile is set,
        this server runs as a HTTPS server.
        """

        # Create TLS context
        if ssl_context and certfile:
            raise TypeError('SSLContext and certfile must not be set at the same time')

        if ssl_context:
            self.ssl = ssl_context
        elif certfile:
            context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
            # context.set_alpn_protocols(['HTTP/1.1', 'h2']) # to enable HTTP/2, add 'h2'
            context.load_cert_chain('server.crt', keyfile='server.key')
            context.options |= ssl.OP_NO_TLSv1 | ssl.OP_NO_TLSv1_1
            self.ssl = context

        self._route = router

    def make_headers(self):
        x = [message.Header('Date', datetime.now(tz=timezone.utc).strftime(util.IMFFixdate)),
             message.Header('Server', 'SimpleServer'),
             message.Header('Content-Type', 'text/html;charset=utf-8'),
            ]
        return message.Headers(headers=x)

    def make_response(self, text):
        status = message.StatusLine('HTTP/1.1', HTTPStatus.OK)
        headers = self.make_headers()
        body = message.ResponseBody.load(text)
        return message.HTTPMessage(status, headers, body)


    def write_error(self, exception, writer):
        status = message.StatusLine('HTTP/1.1', exception.status)
        headers = self.make_headers()
        msg = exception.get_message()
        logger.debug(msg)
        body = message.ResponseBody(msg)
        result = message.HTTPMessage(status, headers, body).save()
        writer.write(result.encode('utf-8'))


    @log
    async def parse(self, data):
        """ Parse HTTP/1.1 request """
        text = data.decode('utf-8')
        request = message.HTTPMessage.load(text)
        return request

    @log
    async def handle_request(self, request, writer):
        """ Handle request and write the result to writer """
        try:
            fn, methods = self._route.find(request.start_line.uri)
            if not request.start_line.method in methods:
                raise message.MethodNotAllowed()

            logger.debug(fn)

            response = await self.call_with_args(fn, request)
            logger.debug(response)
            logger.debug(response.save())

            if isinstance(response, str):
                response = self.make_response(response)

            # append cookie
            for k, v in request.headers.cookie.items():
                if k not in response.headers.cookie:
                    response.headers.set_cookie(k, v)

            writer.write(response.save().encode('utf-8'))

        except KeyError as e:
            logger.warning(e)
            self.write_error(message.NotFound().with_traceback(sys.exc_info()[2]), writer)
        except TypeError as e:
            logger.warning(e)
            e = message.InternalServerError().with_traceback(sys.exc_info()[2])
            self.write_error(e, writer)
        except message.BaseHTTPError as e:
            e = e.with_traceback(sys.exc_info()[2])
            logger.warning(e)
            self.write_error(e, writer)

        await writer.drain()

    async def call_with_args(self, fn, request):
        """ If request body has some key-value pair and fn requires
        the same arguments, this function call the fn with arguments
        supplied in the body.
        """

        sig = signature(fn)
        # delete undeclared parameters
        if request.body:
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

    def get_callback(self):
        @log
        async def client_connected_cb(reader, writer):
            try:
                request_data = await reader.read(8000)
                if False and request_data[:24] == util.HTTP2:
                    logger.info('HTTP/2 connection is requested. {}'.format(len(request_data)))
                    http2 = HTTP2Server(reader, writer)
                    await http2.run()

                else:
                    if reader.at_eof():
                        raise message.RequestEntityTooLarge().with_traceback(sys.exc_info()[2])

                    request = await self.parse(request_data)
                    res = await self.handle_request(request, writer)

            except Exception as e:
                self.write_error(e, writer)

            finally:
                writer.close()

        return client_connected_cb

    async def run(self, port=80):
        rsock_ = create_socket((None, port))
        if self.ssl:
            self.socket = self.ssl.wrap_socket(rsock_, server_side=True)
        await asyncio.start_server(self.get_callback(), sock=self.socket)

    def route(self, method='GET', path='/'):
        return self._route.route(method=method, path=path)

class HTTP2Server(object):
    """docstring for HTTP2Server"""
    def __init__(self, reader, writer):
        self.reader = reader
        self.writer = writer

    async def run(self):
        frame = await self.parse_stream()
        await self.handle_frame(frame)

        my_settings = FrameBase.create(0, FrameTypes.SETTINGS.value, b'\x00', frame.stream_identifier + 1)
        await self.send_frame(my_settings)

        frame = await self.parse_stream()
        await self.handle_frame(frame)

        frame = await self.parse_stream()
        await self.handle_frame(frame)

    async def parse_stream(self):
        data = await self.reader.read(8000) # get setting frame.
        frame = FrameBase.load(data)
        return frame
        
    async def handle_frame(self, frame):
        if frame.FrameType() == FrameTypes.HEADERS:
            pass
        elif frame.FrameType() == FrameTypes.SETTINGS:
            self.initial_window_size = frame.initial_window_size
        elif frame.FrameType() == FrameTypes.WINDOW_UPDATE:
            self.window_size = frame.window_size
            # res = FrameBase.create(0, FrameTypes.SETTINGS.value, b'\x01', frame.stream_identifier + 1)
            # self.writer.write(res.save())
            # await self.writer.drain()

    async def send_frame(self, frame):
        self.writer.write(frame.save())
        await self.writer.drain()
