from http.server import HTTPServer, BaseHTTPRequestHandler
import ssl
import argparse
import asyncio

# private source
import watch

from logger import get_logger, get_log_decorator
logger = get_logger('http')
_log = get_log_decorator('http')

print('HTTPD', __name__)


class MyHTTPServer(object):
    def __init__(self, ssl=None, *args, **kwds):
        self.ssl = ssl


    @_log
    async def parse(self, data):
        """ Tentative implementation """
        import email
        from io import StringIO
        method, header_line = data.decode('utf-8').split('\r\n', 1)

        message = email.message_from_file(StringIO(header_line))
        headers = dict(message.items())

        logger.info('method {}'.format(method))
        logger.debug('message {}'.format(message))
        logger.debug('headers {}'.format(headers))

        return method, headers

    @_log
    async def handle_request(self, request, writer):
        """ Tentative implementation """
        writer.write("this is a test message".encode('utf-8'))
        await writer.drain()
        writer.close()

    def get_callback(self):
        @_log
        async def client_connected_cb(reader, writer):
            logger.debug('in async_http')
            request_data = await reader.read(1000)

            if not request_data:
                writer.close()
            else:
                request = await self.parse(request_data)
                response = await self.handle_request(request, writer)

        return client_connected_cb

    async def run(self, port=80):
        await asyncio.start_server(server.get_callback(), port=port, ssl=self.ssl)


"""Create TLS context"""
context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
context.load_cert_chain('server.crt', keyfile='server.key')
context.options |= ssl.OP_NO_TLSv1 | ssl.OP_NO_TLSv1_1

"""Create HTTP(S) server"""
# server_address = ('', 8000)
# server = MyHTTPServer(server_address, MyHandler)
# server.socket = context.wrap_socket(server.socket,
#     )
server = MyHTTPServer(context)

async def main():
    watcher = watch.Watcher()
    watcher.add_watch(__file__, watch.force_reload(__file__))
    tasks = []
    tasks.append(asyncio.create_task(watcher.watch()))
    tasks.append(server.run(port=8000))

    await asyncio.gather(*tasks)


if __name__ == '__main__':
    import logging
    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(description='Run HTTPS server')
    parser.add_argument('port', metavar='HTTPPORT', type=int, nargs=1, 
        help='port number of this server')

    logger.setLevel(logging.DEBUG)
    hander = logging.StreamHandler()
    hander.setLevel(logging.DEBUG)
    logger.addHandler(hander)

    try:
        asyncio.run(main(), debug=True)
    except KeyboardInterrupt:
        logger.debug('KeyboardInterrupt has happened')

    server.server_close()


# openssl genrsa -out server.key 2048
# openssl req -new -key server.key -out server.csr -batch
# openssl x509 -days 3650 -req -signkey server.key -in server.csr -out server.crt
