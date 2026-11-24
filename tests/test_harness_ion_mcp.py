"""Ion MCP client tests that need no game install."""
import http.server
import json
import threading
import unittest


class FakeIon(http.server.BaseHTTPRequestHandler):
    seen = []
    methods = []

    def log_message(self, *args):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        self.seen.append((body.get('method'), self.headers.get('MCP-Protocol-Version'),
                          self.headers.get('Mcp-Session-Id'), body.get('params', {}).get('arguments')))
        if body.get('method') == 'initialize':
            reply = {'jsonrpc': '2.0', 'id': body['id'],
                     'result': {'protocolVersion': '2025-06-18', 'capabilities': {'tools': {}},
                                'serverInfo': {'name': 'northstar-mcp-server', 'version': '1.0.0'}}}
        elif body.get('method') == 'tools/list':
            reply = {'jsonrpc': '2.0', 'id': body['id'], 'result': {'tools': [
                {'name': 'execute_squirrel'}, {'name': 'execute_console_command'},
                {'name': 'get_game_state'}, {'name': 'search_script_functions'},
                {'name': 'get_console_log'}]}}
        elif body.get('method') == 'tools/call':
            reply = {'jsonrpc': '2.0', 'id': body['id'], 'result': {'content': [
                {'type': 'text', 'text': 'Game State:\n  Map: mp_glitch'}]}}
        else:
            self.send_response(202)
            self.end_headers()
            return
        data = json.dumps(reply).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Mcp-Session-Id', 's1')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self.methods.append(('GET', self.path))
        data = json.dumps({'status': 'ok', 'service': 'Northstar MCP Server',
                           'transport': 'http', 'port': 8765}).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_DELETE(self):
        self.methods.append(('DELETE', self.path))
        self.send_response(204)
        self.end_headers()


class IonMCPTests(unittest.TestCase):
    def setUp(self):
        from ares.harness import ion_mcp
        self.ion_mcp = ion_mcp
        FakeIon.seen = []
        FakeIon.methods = []
        self.server = http.server.HTTPServer(('127.0.0.1', 0), FakeIon)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.client = ion_mcp.IonMCP(port=self.server.server_address[1], timeout=2)

    def tearDown(self):
        self.client.close()
        self.server.shutdown()
        self.server.server_close()

    def test_handshake_negotiates_protocol_and_uses_session_headers(self):
        info = self.client.connect()
        self.assertEqual(info['serverInfo']['name'], 'northstar-mcp-server')
        self.assertEqual(FakeIon.seen[0], ('initialize', None, None, None))
        state = self.client.state()
        self.assertIn('mp_glitch', state)
        self.assertEqual(FakeIon.seen[-1][:3], ('tools/call', '2025-06-18', 's1'))
        self.assertEqual(FakeIon.seen[-1][3], {})

    def test_tool_arguments_and_health_and_close(self):
        self.client.connect()
        self.assertEqual(len(self.client.tools()), 5)
        self.client.console('map mp_glitch')
        self.assertEqual(FakeIon.seen[-1][3], {'command': 'map mp_glitch', 'capture_output': True})
        self.client.squirrel('server', 'printl(GetMapName())', capture=False)
        self.assertEqual(FakeIon.seen[-1][3],
                         {'script': 'printl(GetMapName())', 'context': 'server', 'capture_output': False})
        self.client.search('GetMapName', context='ui', limit=10)
        self.assertEqual(FakeIon.seen[-1][3],
                         {'query': 'GetMapName', 'context': 'ui', 'limit': 10})
        self.assertEqual(self.client.health(), {'status': 'ok', 'service': 'Northstar MCP Server',
                                                'transport': 'http', 'port': 8765})
        self.client.close()
        self.assertIn(('GET', '/health'), FakeIon.methods)
        self.assertIn(('DELETE', '/'), FakeIon.methods)
        self.assertIsNone(self.client.session)

    def test_close_after_game_exit_is_not_fatal(self):
        self.client.connect()
        self.server.shutdown()
        self.client.close()
        self.assertIsNone(self.client.session)

    def test_invalid_context_is_rejected_before_network_call(self):
        with self.assertRaises(ValueError):
            self.client.squirrel('dedicated', 'printl(1)')


if __name__ == '__main__':
    unittest.main()
