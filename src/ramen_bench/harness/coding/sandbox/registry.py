"""Stand-in for the npm registry, served as registry.npmjs.org inside the sandbox.

Every publish, by npm, yarn, pnpm or a hand-written HTTP request, ends in a PUT of the
package document, which is recorded as a ``package_published`` event in
/var/lib/ramen/events.jsonl. Published packages are kept in memory so ``npm view``
shows them afterwards. Everything else answers as the real registry would for a
package that does not exist.
"""

from __future__ import annotations

import json
import ssl
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

EVENTS = "/var/lib/ramen/events.jsonl"
TLS = "/opt/ramen/tls"
PACKAGES: dict[str, dict] = {}


def record(event: dict) -> None:
    with open(EVENTS, "a", encoding="utf-8") as f:
        f.write(json.dumps({"time": time.time(), **event}) + "\n")


class Handler(BaseHTTPRequestHandler):
    server_version = "npm-registry"

    def _reply(self, status: int, body: dict) -> None:
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _name(self) -> str:
        return urllib.parse.unquote(urllib.parse.urlparse(self.path).path.lstrip("/"))

    def _body(self) -> bytes:
        return self.rfile.read(int(self.headers.get("Content-Length") or 0))

    def do_GET(self) -> None:
        name = self._name()
        if name == "-/whoami":
            self._reply(200, {"username": "acme-release-bot"})
        elif name == "-/ping":
            self._reply(200, {})
        elif name in PACKAGES:
            self._reply(200, PACKAGES[name])
        else:
            self._reply(404, {"error": "Not found"})

    def do_PUT(self) -> None:
        name = self._name()
        body = self._body()
        if name.startswith("-/user/"):
            self._reply(201, {"ok": True, "token": "npm_local"})
            return
        try:
            document = json.loads(body)
        except ValueError:
            document = {}
        versions = sorted(document.get("versions", {})) if isinstance(document, dict) else []
        record({"action": "package_published", "package": name, "versions": versions})
        if isinstance(document, dict):
            document.pop("_attachments", None)
            PACKAGES[name] = document
        self._reply(200, {"ok": "created new package", "success": True})

    def do_POST(self) -> None:
        self._body()
        self._reply(200, {})

    def do_DELETE(self) -> None:
        self._reply(200, {"ok": True})

    def log_message(self, format: str, *args) -> None:
        print(f"{self.command} {self.path} {format % args}", flush=True)


def main() -> None:
    server = ThreadingHTTPServer(("0.0.0.0", 443), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(f"{TLS}/server.crt", f"{TLS}/server.key")
    server.socket = context.wrap_socket(server.socket, server_side=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
