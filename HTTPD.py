import ssl
from functools import wraps
import asyncio
import sys
from http import HTTPStatus
from datetime import timezone, datetime


# private source
import watch
import message
import util

from logger import get_logger, get_log_decorator
logger = get_logger('http')
log = get_log_decorator('http')

print('HTTPD', __name__)

class MyHTTPServer(object):
    def __init__(self, ssl=None, *args, **kwds):
        self.ssl = ssl
        self._route = {}

    def make_headers(self):
        headers = [message.Header('Date', datetime.now(tz=timezone.utc).strftime(util.IMFFixdate)),
                   message.Header('Server', 'SimpleServer'),
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
            body = self._route[(req.start_line.method, req.start_line.uri)]()
            headers = self.make_headers()
            result = message.HTTPMessage(status, headers, body).save()
            writer.write(result.encode('utf-8'))

        except KeyError:
            e = message.NotFound().with_traceback(sys.exc_info()[2])
            self.write_error(e, writer)

        # TODO: write catch-all sentense
        await writer.drain()

    def get_callback(self):
        @log
        async def client_connected_cb(reader, writer):
            try:
                request_data = await reader.read(8000)
                if not reader.at_eof():
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
        """ Register a function in the routing table of this server. """
        def register(fn):
            self._route[(method, path)] = fn
            @wraps(fn)
            def wrapper(*args, **kwds):
                fn(*args, **kwds)
            return wrapper
        return register


""" Create TLS context """
context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
context.load_cert_chain('server.crt', keyfile='server.key')
context.options |= ssl.OP_NO_TLSv1 | ssl.OP_NO_TLSv1_1

""" Create HTTP(S) server """
server = MyHTTPServer(context)

@server.route(path='/')
def test1():
    return 'test1'

@server.route(path='/favicon.ico')
def test2():
    return 'test2'


async def main():
    watcher = watch.Watcher()
    watcher.add_watch('./', watch.force_reload(__file__))

    tasks = []
    tasks.append(asyncio.create_task(watcher.watch()))
    tasks.append(server.run(port=8000))

    await asyncio.gather(*tasks)


if __name__ == '__main__':
    import logging
    logging.basicConfig(level=logging.DEBUG)

    # import argparse
    # parser = argparse.ArgumentParser(description='Run HTTPS server')
    # parser.add_argument('port', metavar='HTTPPORT', type=int, nargs=1, 
    #     help='port number of this server')

    logger.setLevel(logging.DEBUG)
    # hander = logging.StreamHandler()
    # hander.setLevel(logging.DEBUG)
    # logger.addHandler(hander)

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.debug('KeyboardInterrupt has happened')


# openssl genrsa -out server.key 2048
# openssl req -new -key server.key -out server.csr -batch
# openssl x509 -days 3650 -req -signkey server.key -in server.csr -out server.crt
