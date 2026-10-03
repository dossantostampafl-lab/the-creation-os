"""Fixed-destination TCP relay used only to publish isolated Range targets on host loopback."""
from __future__ import annotations

import os
import selectors
import socket
import socketserver


LISTEN_PORT = int(os.environ["LISTEN_PORT"])
TARGET_HOST = os.environ["TARGET_HOST"]
TARGET_PORT = int(os.environ["TARGET_PORT"])


class Relay(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        upstream = socket.create_connection((TARGET_HOST, TARGET_PORT), timeout=5)
        try:
            self.request.setblocking(False)
            upstream.setblocking(False)
            selector = selectors.DefaultSelector()
            selector.register(self.request, selectors.EVENT_READ, upstream)
            selector.register(upstream, selectors.EVENT_READ, self.request)
            while True:
                ready = selector.select(timeout=30)
                if not ready:
                    continue
                for key, _ in ready:
                    peer = key.data
                    data = key.fileobj.recv(65536)
                    if not data:
                        return
                    peer.sendall(data)
        finally:
            upstream.close()


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


if __name__ == "__main__":
    with Server(("0.0.0.0", LISTEN_PORT), Relay) as server:
        server.serve_forever()
