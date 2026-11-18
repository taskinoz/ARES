import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import tempfile
import threading
import unittest

from r5_harnessctl import call


class ClientTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.connection = Path(temporary.name) / 'connection.json'

    def save(self, url):
        self.connection.write_text(json.dumps({'url': url, 'token': 'test-only-token'}))

    def test_rejects_credential_exfiltration_urls(self):
        for url in ('http://127.0.0.1:80@remote.invalid', 'http://127.0.0.1:80/path',
                    'http://127.0.0.1:80?query', 'http://127.0.0.1:80#fragment',
                    'https://127.0.0.1:80', 'http://127.0.0.1', 'http://127.0.0.1:0',
                    'http://127.0.0.1:65536', 'http://127.0.0.1:invalid', 'http://localhost:80'):
            with self.subTest(url=url):
                self.save(url)
                with self.assertRaises(ValueError):
                    call(self.connection, 'state')

    def server(self, handler):
        server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        def close():
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
        self.addCleanup(close)
        return f'http://127.0.0.1:{server.server_port}'

    def test_round_trip_authentication(self):
        received = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                received.append((self.path, self.headers.get('Authorization')))
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"ready": true}')
        self.save(self.server(Handler))
        self.assertEqual(call(self.connection, 'state'), {'ready': True})
        self.assertEqual(received, [('/state', 'Bearer test-only-token')])
        with self.assertRaisesRegex(ValueError, 'endpoint'):
            call(self.connection, '../other')

    def test_redirects_are_not_followed_even_to_loopback(self):
        received = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                received.append(self.path)
                self.send_response(302)
                self.send_header('Location', '/leak')
                self.end_headers()
        self.save(self.server(Handler))
        with self.assertRaises(RuntimeError):
            call(self.connection, 'state')
        self.assertEqual(received, ['/state'])


if __name__ == '__main__':
    unittest.main()
