"""Tunnel-facing shim: 302 the bare root to the dashboard, proxy everything
else to Perses, injecting a monospace font override into HTML responses
(the Perses SPA is embedded in its binary, so CSS cannot live there).
ponytail: stdlib proxy, one viewer; swap for caddy if it ever matters."""
import http.server
import urllib.error
import urllib.request
from socketserver import ThreadingMixIn

UP = "http://127.0.0.1:8080"
DASH = "/projects/llm/dashboards/llm-quota-native"
CSS = (b"<style>*{font-family:ui-monospace,\x27Cascadia Mono\x27,"
       b"\x27JetBrains Mono\x27,\x27Fira Code\x27,\x27Courier New\x27,"
       b"monospace !important;}</style>")

class P(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self):
        self.proxy("GET")

    def do_POST(self):
        self.proxy("POST")

    def do_PUT(self):
        self.proxy("PUT")

    def do_DELETE(self):
        self.proxy("DELETE")

    def proxy(self, method):
        if self.path == "/":
            self.send_response(302)
            self.send_header("Location", DASH)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        body = None
        if method in ("POST", "PUT"):
            ln = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(ln) if ln else b""
        req = urllib.request.Request(UP + self.path, data=body, method=method)
        for k, v in self.headers.items():
            if k.lower() not in ("host", "accept-encoding", "connection", "content-length"):
                req.add_header(k, v)
        req.add_header("Accept-Encoding", "identity")
        try:
            resp = urllib.request.urlopen(req, timeout=60)
        except urllib.error.HTTPError as e:
            resp = e
        except Exception:
            self.send_response(502)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        data = resp.read()
        ct = resp.headers.get("Content-Type", "")
        if "text/html" in ct and b"</head>" in data:
            data = data.replace(b"</head>", CSS + b"</head>", 1)
        self.send_response(getattr(resp, "status", resp.code))
        for k in ("Content-Type", "Cache-Control", "Location"):
            if resp.headers.get(k):
                self.send_header(k, resp.headers[k])
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass

class T(ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True

T(("127.0.0.1", 8081), P).serve_forever()
