from http.server import HTTPServer, BaseHTTPRequestHandler
import ssl

class MyHandler(BaseHTTPRequestHandler):
    pass


"""Create TLS context"""
# context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH, cafile='server.crt')
context.load_cert_chain('server.crt', keyfile='server.key')
context.options |= ssl.OP_NO_TLSv1 | ssl.OP_NO_TLSv1_1

"""Create HTTP(S) server"""
server_address = ('', 8000)
server = HTTPServer(server_address, MyHandler)
server.socket = context.wrap_socket(server.socket,
	                           )


if __name__ == '__main__':
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    server.server_close()


# openssl genrsa -out server.key 2048
# openssl req -new -key server.key -out server.csr -batch
# openssl x509 -days 3650 -req -signkey server.key -in server.csr -out server.crt
