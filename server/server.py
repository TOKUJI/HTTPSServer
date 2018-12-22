from functools import wraps
from inspect import signature, iscoroutinefunction, iscoroutine
import asyncio
import sys
from http import HTTPStatus
from datetime import timezone, datetime
# from urllib.parse import urlparse, parse_qs

# private library
import message
import util

from logger import get_logger_set
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
             # message.Header('Content-Encoding', ''),
             # message.Header('Content-Language', ''),
             # message.Header('Content-Location ', 'Tokyo/Japan'),
        ]
        return message.Headers({h.key:h.value for h in x})

    def make_response(self, text):
        status = message.StatusLine('HTTP/1.1', HTTPStatus.OK)
        headers = self.make_headers()
        body, _ = message.ResponseBody.load(text)
        return message.HTTPMessage(status, headers, body)


    def write_error(self, exception, writer):
        status = message.StatusLine('HTTP/1.1', exception.status)
        headers = self.make_headers()
        body = '{} {}'.format(exception.status.value, exception.status.phrase)
        logger.warning(body)
        result = message.HTTPMessage(status, headers, body).save()
        writer.write(result.encode('utf-8'))


    @log
    async def parse(self, data):
        """ Parse HTTP/1.1 request """
        text = data.decode('utf-8')
        req, _ = message.HTTPMessage.load(text)
        return req

    @log
    async def handle_request(self, req, writer):
        """ Handle request and write the result to writer """
        try:
            fn = self._route.find(req.start_line.method, req.start_line.uri)
            response = await self.call_with_args(fn, req)
            logger.info(response)

            if isinstance(response, str):
                response = self.make_response(response)

            writer.write(response.save().encode('utf-8'))

        except KeyError as e:
            logger.warning(e)
            self.write_error(message.NotFound().with_traceback(sys.exc_info()[2]), writer)
        except TypeError as e:
            e = message.InternalServerError().with_traceback(sys.exc_info()[2])
            self.write_error(e, writer)

        await writer.drain()

    async def call_with_args(self, fn, req):
        """ If request body has some key-value pair and fn requires
        the same arguments, this function call the fn with arguments
        supplied in the body.
        """

        sig = signature(fn)
        if 'request' in sig.parameters.keys():
            bn = sig.bind(request=req, **req.body.data)
        else:
            bn = sig.bind(**req.body.data)

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

                req = await self.parse(request_data)
                res = await self.handle_request(req, writer)

            except Exception as e:
                self.write_error(e, writer)

            finally:
                writer.close()

        return client_connected_cb

    async def run(self, port=80):
        await asyncio.start_server(self.get_callback(), port=port, ssl=self.ssl)

    def route(self, method='GET', path='/'):
        return self._route.route(method=method, path=path)

    def keep_cookie(self, fn):
        @wraps
        def wrapper(request, *args, **kwds):
            res = fn(*args, **kwds)
            for k, v in request.headers.cookie.items():
                logger.info('{}:{}'.format(k, v))
                if k not in res.headers.cookie:
                    res.headers.cookie[k] = v
            return res
        return wrapper
