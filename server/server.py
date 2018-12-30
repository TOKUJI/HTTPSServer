from functools import wraps
from inspect import signature, iscoroutine
import asyncio
import sys
from http import HTTPStatus
from datetime import timezone, datetime
# from urllib.parse import urlparse, parse_qs

# private library
# from .message import *
from . import message
from . import util

from .logger import get_logger_set
logger, log = get_logger_set('server')


class MyHTTPServer(object):
    def __init__(self, ssl =None,
                 router = util.RouteRecord(),
                 *args, **kwds):
        """ HTTP Server class.
        """
        self.ssl = ssl
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
        request, _ = message.HTTPMessage.load(text)
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
        await asyncio.start_server(self.get_callback(), port=port, ssl=self.ssl)

    def route(self, method='GET', path='/'):
        return self._route.route(method=method, path=path)
