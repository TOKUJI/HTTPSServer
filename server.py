from functools import wraps
import asyncio
import sys
from http import HTTPStatus
from datetime import timezone, datetime
from urllib.parse import urlparse, parse_qs

# private library
import message
import util

from logger import get_logger_set
logger, log = get_logger_set('server')


class MyHTTPServer(object):
    def __init__(self, ssl=None, *args, **kwds):
        self.ssl = ssl
        self._route = util.RouteRecord()

    def make_headers(self):
        headers = [message.Header('Date', datetime.now(tz=timezone.utc).strftime(util.IMFFixdate)),
                   message.Header('Server', 'SimpleServer'),
                   message.Header('Content-Type', 'text/html;charset=utf-8'),
                   # message.Header('Content-Encoding', ''),
                   # message.Header('Content-Language', ''),
                   # message.Header('Content-Location ', 'Tokyo/Japan'),
        ]
        return headers

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
            status = message.StatusLine('HTTP/1.1', HTTPStatus.OK)
            body = self.match(req.start_line.method, req.start_line.uri)()
            headers = self.make_headers()
            result = message.HTTPMessage(status, headers, body).save()
            writer.write(result.encode('utf-8'))

        except KeyError as e:
            logger.warning(e)
            self.write_error(message.NotFound().with_traceback(sys.exc_info()[2]), writer)
        except TypeError as e:
            e = message.InternalServerError().with_traceback(sys.exc_info()[2])
            self.write_error(e, writer)

        await writer.drain()

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

    def match(self, method, path):
        m = self._route[path]
        if m[-1] == method:
            logger.info('{} is mathced'.format(path))
            return m[0]
        else:
            raise KeyError('{} is not registered on the method {}'.format(path, method))

    def route(self, method='GET', path='/'):
        """ Register a function in the routing table of this server. """
        def register(fn):
            self._route[path] = (fn, method)
            @wraps(fn)
            def wrapper(*args, **kwds):
                logger.info('wrapper is called')
                fn(*args, **kwds)
            return wrapper
        return register
