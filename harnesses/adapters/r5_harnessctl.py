#!/usr/bin/env python3
"""Call the localhost map harness without exposing its token in shell history.

Original implementation, GPL-2.0-or-later.
"""
import argparse
import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        return None


def call(connection_path, endpoint, data=None, timeout=100):
    connection = json.loads(Path(connection_path).read_text())
    address = urlsplit(connection['url'])
    if (address.scheme != 'http' or address.hostname != '127.0.0.1' or
            address.username is not None or address.password is not None or
            address.port is None or not 1 <= address.port <= 65535 or
            address.path or address.query or address.fragment):
        raise ValueError('Expected a loopback harness URL')
    if endpoint not in ('boot', 'load', 'command', 'state', 'events', 'stop'):
        raise ValueError('Unknown harness endpoint')
    request = Request(connection['url'] + '/' + endpoint,
                      data=json.dumps(data).encode() if data is not None else None,
                      headers={'Authorization': 'Bearer ' + connection['token'],
                               'Content-Type': 'application/json'})
    try:
        with build_opener(ProxyHandler({}), NoRedirects()).open(request, timeout=timeout) as response:
            return json.load(response)
    except HTTPError as error:
        raise RuntimeError(error.read().decode()) from None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--connection', type=Path, required=True)
    parser.add_argument('endpoint', choices=('boot', 'load', 'command', 'state', 'events', 'stop'))
    parser.add_argument('json', nargs='?', default=None, help='JSON request object for POST endpoints')
    args = parser.parse_args()
    data = json.loads(args.json or '{}') if args.endpoint not in ('state', 'events') else None
    print(json.dumps(call(args.connection, args.endpoint, data), indent=2))


if __name__ == '__main__':
    main()
