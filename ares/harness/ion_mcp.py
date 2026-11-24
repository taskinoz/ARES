"""Client for Ion's built-in MCP server (R2 / Titanfall 2 Northstar fork).

Ion compiles a Streamable HTTP MCP server into ``R2Northstar/Northstar.dll``;
it is not a separate download or plugin. Start it with ``+mcp_start_http PORT``
(the default port is 8765). The server binds 127.0.0.1 only, requires an
initialize handshake and a ``Mcp-Session-Id`` on later requests, and speaks
JSON-RPC 2.0 at ``POST /`` with ``GET /health`` for a readiness probe.

Tools exposed by Ion v1.31.15: ``execute_squirrel``, ``execute_console_command``,
``get_game_state``, ``search_script_functions`` and ``get_console_log``.
This client uses the standard library only and never starts the game.

  python -m ares.harness.ion_mcp --port 8766 state
  python -m ares.harness.ion_mcp --port 8766 console "map mp_glitch"
  python -m ares.harness.ion_mcp --port 8766 squirrel server "printl(GetMapName())"
  python -m ares.harness.ion_mcp --port 8766 search "GetMapName"
"""
import argparse
import itertools
import json
import sys
import time
import urllib.error
import urllib.request

PROTOCOL = '2025-06-18'
DEFAULT_PORT = 8765


class IonMCP:
    """Small JSON-RPC client for the loopback MCP endpoint in Ion."""

    def __init__(self, port=DEFAULT_PORT, path='/', timeout=60, host='127.0.0.1'):
        self.url = 'http://%s:%d%s' % (host, port, path)
        self.timeout = timeout
        self.session = None
        self.ids = itertools.count(1)
        self.protocol = None  # sent only after initialize negotiates it
        self.initialized = None

    def _post(self, payload):
        headers = {'Content-Type': 'application/json', 'Accept': 'application/json, text/event-stream'}
        if self.protocol:
            headers['MCP-Protocol-Version'] = self.protocol
        if self.session:
            headers['Mcp-Session-Id'] = self.session
        request = urllib.request.Request(self.url, json.dumps(payload).encode(), headers, method='POST')
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            self.session = response.headers.get('Mcp-Session-Id') or self.session
            body = response.read().decode('utf-8', 'replace')
            if 'text/event-stream' in (response.headers.get('Content-Type') or ''):
                data = [line[5:].strip() for line in body.splitlines() if line.startswith('data:')]
                body = data[-1] if data else ''
        return json.loads(body) if body.strip() else None

    def connect(self):
        reply = self._post({'jsonrpc': '2.0', 'id': next(self.ids), 'method': 'initialize',
                            'params': {'protocolVersion': PROTOCOL, 'capabilities': {},
                                       'clientInfo': {'name': 'ares-ion-mcp', 'version': '1'}}})
        # Ion rejects an unnegotiated version header; later requests use its answer.
        self.protocol = reply['result'].get('protocolVersion', PROTOCOL)
        self._post({'jsonrpc': '2.0', 'method': 'notifications/initialized'})
        self.initialized = reply['result']
        return self.initialized

    def close(self):
        """Drop the server-side session. The DELETE endpoint returns 204.

        Ion may already have exited by cleanup time, so a failed close is not
        an error: the session is always discarded locally.
        """
        if not self.session:
            return
        request = urllib.request.Request(self.url, headers={'Mcp-Session-Id': self.session}, method='DELETE')
        try:
            with urllib.request.urlopen(request, timeout=self.timeout):
                pass
        except (urllib.error.URLError, ConnectionError, TimeoutError, OSError):
            pass
        finally:
            self.session = None
            self.initialized = None

    def request(self, method, params=None):
        payload = {'jsonrpc': '2.0', 'id': next(self.ids), 'method': method}
        if params is not None:
            payload['params'] = params
        reply = self._post(payload)
        if reply is None:
            return None
        if 'error' in reply:
            raise RuntimeError('%s: %s' % (method, reply['error']))
        return reply.get('result')

    def call(self, tool, **arguments):
        result = self.request('tools/call', {'name': tool, 'arguments': arguments})
        if result is None:
            return ''
        text = '\n'.join(c.get('text', '') for c in result.get('content', []) if c.get('type') == 'text')
        if result.get('isError'):
            raise RuntimeError('%s failed: %s' % (tool, text))
        return text

    def tools(self):
        result = self.request('tools/list')
        return result['tools'] if result else []

    def console(self, command, capture=True):
        return self.call('execute_console_command', command=command, capture_output=capture)

    def squirrel(self, context, script, capture=True):
        if context not in ('server', 'client', 'ui'):
            raise ValueError('context must be server, client or ui')
        return self.call('execute_squirrel', context=context, script=script, capture_output=capture)

    def state(self):
        return self.call('get_game_state')

    def log(self):
        return self.call('get_console_log')

    def search(self, query, context='server', limit=50, **extra):
        arguments = {'query': query, 'context': context, 'limit': limit}
        arguments.update(extra)
        return self.call('search_script_functions', **arguments)

    def health(self, timeout=5):
        with urllib.request.urlopen(self.url.rsplit('/', 1)[0] + '/health', timeout=timeout) as response:
            return json.loads(response.read().decode('utf-8', 'replace'))


def wait_for_server(port=DEFAULT_PORT, timeout=300, **kwargs):
    """Connect once the game has started its MCP listener (or raise on timeout)."""
    deadline = time.monotonic() + timeout
    while True:
        client = IonMCP(port=port, **kwargs)
        try:
            client.connect()
            return client
        except (urllib.error.URLError, ConnectionError, TimeoutError, OSError):
            if time.monotonic() > deadline:
                raise
            time.sleep(2)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--port', type=int, default=DEFAULT_PORT)
    p.add_argument('--host', default='127.0.0.1')
    sub = p.add_subparsers(dest='action', required=True)
    sub.add_parser('state')
    sub.add_parser('log')
    sub.add_parser('tools')
    sub.add_parser('health')
    c = sub.add_parser('console')
    c.add_argument('command')
    s = sub.add_parser('squirrel')
    s.add_argument('context', choices=('server', 'client', 'ui'))
    s.add_argument('script')
    f = sub.add_parser('search')
    f.add_argument('query')
    f.add_argument('--context', choices=('server', 'client', 'ui'), default='server')
    a = p.parse_args(argv)
    client = IonMCP(port=a.port, host=a.host)
    client.connect()
    try:
        if a.action == 'state':
            print(client.state())
        elif a.action == 'log':
            print(client.log())
        elif a.action == 'tools':
            print(json.dumps([t['name'] for t in client.tools()]))
        elif a.action == 'health':
            print(json.dumps(client.health()))
        elif a.action == 'console':
            print(client.console(a.command))
        elif a.action == 'squirrel':
            print(client.squirrel(a.context, a.script))
        else:
            print(client.search(a.query, a.context))
    finally:
        client.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
