import ssl
import asyncio

# private library
import server
import watch
from util import URI
from logger import get_logger_set, ColoredFormatter
logger, log = get_logger_set()


""" Create TLS context """
context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
context.load_cert_chain('server.crt', keyfile='server.key')
context.options |= ssl.OP_NO_TLSv1 | ssl.OP_NO_TLSv1_1

""" Create HTTP(S) server """
app = server.MyHTTPServer(context)

@app.route(path='/')
def test1():
    return 'test1'

@app.route(path='/favicon.ico')
def test2():
    return 'test2'

@app.route(path=URI)
def all_catch():
    return 'catched'


async def main():
    watcher = watch.Watcher()
    watcher.add_watch('./', watch.force_reload(__file__))

    tasks = []
    tasks.append(asyncio.create_task(watcher.watch()))
    tasks.append(app.run(port=8000))

    await asyncio.gather(*tasks)


if __name__ == '__main__':
    print('========================================================')
    import logging

    logger.setLevel(logging.DEBUG)

    handler = logging.StreamHandler()
    handler.setLevel(logging.DEBUG)
    cf = ColoredFormatter('%(levelname)-17s:%(name)s %(message)s')
    handler.setFormatter(cf)
    logger.addHandler(handler)

    # import argparse
    # parser = argparse.ArgumentParser(description='Run HTTPS server')
    # parser.add_argument('port', metavar='HTTPPORT', type=int, nargs=1, 
    #     help='port number of this server')

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.debug('KeyboardInterrupt has happened')


# openssl genrsa -out server.key 2048
# openssl req -new -key server.key -out server.csr -batch
# openssl x509 -days 3650 -req -signkey server.key -in server.csr -out server.crt
