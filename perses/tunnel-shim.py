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
CSS = (b"<style>"
       b"*{font-family:ui-monospace,\x27Cascadia Mono\x27,\x27JetBrains Mono\x27,"
       b"\x27Fira Code\x27,\x27Courier New\x27,monospace !important;"
       b"border-radius:0 !important;}"
       b"html,body{background:#030503 !important;}"
       b"body::after{content:\x27\x27;position:fixed;inset:0;pointer-events:none;"
       b"z-index:99999;background:repeating-linear-gradient(0deg,rgba(0,0,0,.18) 0 1px,transparent 1px 3px);}"
       b".MuiAppBar-root{background:#030503 !important;border-bottom:1px solid #00ff41;box-shadow:none !important;}"
       b".MuiPaper-root,.MuiCard-root{background:#040804 !important;border:1px solid #114a22 !important;box-shadow:none !important;}"
       b"body,.MuiTypography-root,.MuiTableCell-root,.MuiButtonBase-root,input,span{color:#9dffb0 !important;}"
       b"h1,h2,h3,h4,h5,h6,.MuiTypography-h6,.MuiTypography-subtitle1"
       b"{color:#00ff41 !important;text-shadow:0 0 6px rgba(0,255,65,.45);}"
       b"a{color:#00ff41 !important;}"
       b".MuiInputBase-root,.MuiOutlinedInput-root{background:#0a120a !important;}"
       b"::selection{background:#00ff41;color:#000;}"
       b".MuiAppBar-root,header.MuiAppBar-root,.MuiAppBar-colorPrimary{background-color:#030503 !important;background-image:none !important;}"
       b"#root,main{background:#030503 !important;}"
       b".MuiBox-root{background-color:transparent !important;}"
       b"div.MuiToolbar-root.MuiToolbar-regular,header div.MuiToolbar-root{background-color:#030503 !important;background-image:none !important;}"
       b"table.MuiTable-root,tr.MuiTableRow-root,td.MuiTableCell-root,th.MuiTableCell-root{background-color:transparent !important;}"
       b"</style>")

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
        html = "text/html" in ct
        if html and b"</head>" in data:
            data = data.replace(b"</head>", CSS + b"</head>", 1)
        self.send_response(getattr(resp, "status", resp.code))
        for k in ("Content-Type", "Location"):
            if resp.headers.get(k):
                self.send_header(k, resp.headers[k])
        self.send_header("Cache-Control", "no-store" if html else resp.headers.get("Cache-Control", "no-cache"))
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass

class T(ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True

T(("127.0.0.1", 8081), P).serve_forever()
