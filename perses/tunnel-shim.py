"""Tunnel-facing shim: 302 the bare root to the dashboard, enforce a
read-only public surface, and proxy the rest to Perses while injecting the
terminal skin into HTML responses (the Perses SPA is embedded in its binary,
so CSS cannot live there).

Perses itself runs with anonymous access; the tunnel reaches it ONLY through
this shim, so `public_allows` below is the entire internet-facing surface.
Administration stays reachable on the LAN at http://<host>:8080.
ponytail: stdlib proxy, one viewer; swap for caddy if it ever matters."""
import http.server
import re
import urllib.error
import urllib.request
from socketserver import ThreadingMixIn

UP = "http://127.0.0.1:8080"
DASH = "/projects/llm/dashboards/llm-quota-native"

# Datasource-proxy paths that only READ. Everything else through /proxy/ is a
# route into whatever the datasource points at (Prometheus remote-write, OTLP
# ingest, admin TSDB endpoints), so the proxy is allowlisted, not filtered.
READ_QUERY = re.compile(
    r"^/proxy/(?:global)?datasources/[^/]+/api/v1/"
    r"(?:query|query_range|series|labels|label/[^/]+/values|metadata|format_query)$"
)
# The dashboard's charts fetch data by POST, so POST cannot be blanket-denied.
POST_ALLOWED = (READ_QUERY, re.compile(r"^/api/v1/view$"))
# Admin resources the dashboard never needs; reads would leak accounts/secrets.
GET_DENIED = re.compile(
    r"^/api/v1/(?:users|roles|rolebindings|globalroles|globalrolebindings"
    r"|secrets|globalsecrets)\b"
)


def public_allows(method, path):
    """True if an anonymous request from the internet may proceed."""
    path = path.split("?", 1)[0]
    if method in ("GET", "HEAD"):
        if GET_DENIED.match(path):
            return False
        if path.startswith("/proxy/") and not READ_QUERY.match(path):
            return False
        return True
    if method == "POST":
        return any(p.match(path) for p in POST_ALLOWED)
    return False  # PUT/PATCH/DELETE: every resource mutation is refused.


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

DENIED = b"403 read-only: administration is available on the LAN only\n"


class P(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self):
        self.proxy("GET")

    def do_POST(self):
        self.proxy("POST")

    def do_PUT(self):
        self.proxy("PUT")

    def do_PATCH(self):
        self.proxy("PATCH")

    def do_DELETE(self):
        self.proxy("DELETE")

    def proxy(self, method):
        if not public_allows(method, self.path):
            # Drain the body so the connection stays usable for keep-alive.
            ln = int(self.headers.get("Content-Length") or 0)
            if ln:
                self.rfile.read(ln)
            self.send_response(403)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(DENIED)))
            self.end_headers()
            self.wfile.write(DENIED)
            return
        if self.path == "/":
            self.send_response(302)
            self.send_header("Location", DASH)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        body = None
        if method in ("POST", "PUT", "PATCH"):
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


def _self_check():
    """Assert the policy: charts keep working, administration does not."""
    allowed = [
        ("GET", "/projects/llm/dashboards/llm-quota-native"),
        ("GET", "/api/v1/projects/llm/dashboards/llm-quota-native"),
        ("GET", "/plugins/TimeSeriesChart/mf-manifest.json"),
        ("POST", "/proxy/globaldatasources/prometheus/api/v1/query_range"),
        ("POST", "/proxy/globaldatasources/prometheus/api/v1/query?query=up"),
        ("POST", "/api/v1/view"),
    ]
    denied = [
        ("POST", "/api/v1/globaldatasources"),          # SSRF: new datasource
        ("PUT", "/api/v1/projects/llm/dashboards/x"),   # dashboard tamper
        ("DELETE", "/api/v1/projects/llm"),             # destruction
        ("PATCH", "/api/v1/globaldatasources/prometheus"),
        ("GET", "/api/v1/users"),                       # account enumeration
        ("GET", "/api/v1/globalsecrets"),               # credential read
        ("POST", "/proxy/globaldatasources/prometheus/api/v1/otlp/v1/metrics"),  # metric injection
        ("GET", "/proxy/globaldatasources/prometheus/api/v1/admin/tsdb/delete_series"),
    ]
    for m, p in allowed:
        assert public_allows(m, p), f"should allow {m} {p}"
    for m, p in denied:
        assert not public_allows(m, p), f"should deny {m} {p}"
    print(f"policy self-check ok: {len(allowed)} allowed, {len(denied)} denied")


if __name__ == "__main__":
    import sys

    if "--self-check" in sys.argv:
        _self_check()
    else:
        T(("127.0.0.1", 8081), P).serve_forever()
