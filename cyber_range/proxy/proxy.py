"""Fixed-destination TCP relay used only to publish isolated Range targets on host loopback."""
from __future__ import annotations

import os
import selectors
import socket
import socketserver
from typing import NamedTuple

_ALLOWED_DESTINATIONS = {
    ("controller", 7070),
    ("juice-shop", 3000),
    ("webgoat", 8080),
    ("webgoat", 9090),
}


class ProxyConfig(NamedTuple):
    listen_port: int
    target_host: str
    target_port: int


def config_from_env(env: dict[str, str] | None = None) -> ProxyConfig:
    values = os.environ if env is None else env
    try:
        listen_port = int(values["LISTEN_PORT"])
        target_host = values["TARGET_HOST"]
        target_port = int(values["TARGET_PORT"])
    except (KeyError, ValueError) as exc:
        raise ValueError("proxy configuration is incomplete") from exc
    if not 1 <= listen_port <= 65535 or (target_host, target_port) not in _ALLOWED_DESTINATIONS:
        raise ValueError("proxy destination is not an allowlisted Cyber Range target")
    return ProxyConfig(listen_port, target_host, target_port)


def _send_all(sock: socket.socket, data: bytes) -> None:
    view = memoryview(data)
    while view:
        try:
            sent = sock.send(view)
        except BlockingIOError:
            _, writable, _ = select_ready([], [sock])
            if not writable:
                continue
            sent = 0
        if sent > 0:
            view = view[sent:]


def select_ready(readers: list[socket.socket], writers: list[socket.socket]):
    import select

    return select.select(readers, writers, [], 5)


class Relay(socketserver.BaseRequestHandler):
    config: ProxyConfig

    def handle(self) -> None:
        upstream = socket.create_connection(
            (self.config.target_host, self.config.target_port),
            timeout=5,
        )
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
                    try:
                        data = key.fileobj.recv(65536)
                    except BlockingIOError:
                        continue
                    if not data:
                        return
                    _send_all(peer, data)
        finally:
            upstream.close()


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def serve(config: ProxyConfig) -> None:
    class ConfiguredRelay(Relay):
        pass

    ConfiguredRelay.config = config
    with Server(("0.0.0.0", config.listen_port), ConfiguredRelay) as server:
        server.serve_forever()


if __name__ == "__main__":
    serve(config_from_env())
