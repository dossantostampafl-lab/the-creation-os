"""Private host relay to the loopback controller, without exposing vulnerable targets.

Run on the host as an unprivileged user. Requires an explicit private bind IP and
CYBER_RANGE_CONTROL_TOKEN. It has no Docker socket or production credentials.
"""
from __future__ import annotations

import argparse
import hmac
import ipaddress
import os
import re
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def allowed(method: str, path: str) -> bool:
    if method == 'GET':
        return path in {'/health', '/state', '/scenarios', '/snapshots'}
    return method == 'POST' and (path in {'/reset', '/snapshots'} or bool(re.fullmatch(
        r'/scenarios/[A-Za-z0-9][A-Za-z0-9_-]{0,63}/start|/snapshots/[a-f0-9-]{36}/restore', path)))


def serve(bind: str, port: int, token: str) -> ThreadingHTTPServer:
    address = ipaddress.ip_address(bind)
    if not address.is_private or address.is_unspecified or address.is_multicast or len(token) < 32:
        raise ValueError('explicit private bind IP and token of at least 32 characters required')

    class Handler(BaseHTTPRequestHandler):
        def handle_call(self):
            if not hmac.compare_digest(self.headers.get('Authorization', ''), 'Bearer ' + token):
                self.send_error(401)
                return
            if not allowed(self.command, self.path):
                self.send_error(404)
                return
            # These lifecycle endpoints do not accept a request body.
            if self.headers.get('Transfer-Encoding') or self.headers.get('Content-Length', '0') != '0':
                self.send_error(413)
                return
            request = urllib.request.Request('http://127.0.0.1:7070' + self.path, method=self.command,
                                             data=b'' if self.command == 'POST' else None)
            try:
                opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                with opener.open(request, timeout=5) as upstream:
                    body = upstream.read(2*1024*1024+1)
                    status = upstream.status
                if len(body) > 2*1024*1024:
                    self.send_error(502)
                    return
            except urllib.error.HTTPError as exc:
                body = b'{"detail":"Range action rejected"}'
                status = exc.code
            except (OSError, urllib.error.URLError):
                body = b'{"detail":"Range controller offline"}'
                status = 503
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        do_GET = handle_call
        do_POST = handle_call

        def log_message(self, format, *args):
            pass  # Never log authorization headers or request bodies.

    server = ThreadingHTTPServer((bind, port), Handler)
    server.timeout = 5
    return server


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--bind', required=True)
    parser.add_argument('--port', type=int, default=7071)
    args = parser.parse_args()
    serve(args.bind, args.port, os.environ.get('CYBER_RANGE_CONTROL_TOKEN', '')).serve_forever()
