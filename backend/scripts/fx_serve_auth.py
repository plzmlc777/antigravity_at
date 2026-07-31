"""Token/cookie static server for the FX dashboard (localhost only, behind cloudflared).
First visit with ?k=<TOKEN> sets a long-lived cookie, then no prompt ever again.
Serves ONLY /index.html. Token read from ~/fx_site/.auth (single line, chmod 600).
"""
import os, re, sqlite3, http.server, socketserver
from http.cookies import SimpleCookie
from urllib.parse import urlparse, parse_qs

HOME = os.path.expanduser("~")
SITE = os.path.join(HOME, "fx_site")
TOKEN = open(os.path.join(SITE, ".auth")).read().strip()
INDEX = os.path.join(SITE, "index.html")
JDB = os.path.join(SITE, "data", "judgments.db")
COOKIE = "fxauth"
MAXAGE = 315360000  # ~10 years

DENY_HTML = b"""<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>body{background:#0d1117;color:#e6edf3;font-family:system-ui,-apple-system,sans-serif;
display:flex;align-items:center;justify-content:center;height:100vh;margin:0;text-align:center}
div{padding:24px}h1{font-size:18px}p{color:#8b949e;font-size:13px}</style></head>
<body><div><h1>\xf0\x9f\x94\x92 \xec\xa0\x91\xea\xb7\xbc \xeb\xa7\x81\xed\x81\xac\xea\xb0\x80 \xed\x95\x84\xec\x9a\x94\xed\x95\xa9\xeb\x8b\x88\xeb\x8b\xa4</h1>
<p>\xeb\xb0\x9b\xec\x9c\xbc\xec\x8b\xa0 \xec\xa0\x84\xec\x9a\xa9 \xeb\xa7\x81\xed\x81\xac\xeb\xa1\x9c \xec\xa0\x91\xec\x86\x8d\xed\x95\xb4 \xec\xa3\xbc\xec\x84\xb8\xec\x9a\x94.</p></div></body></html>"""


class Handler(http.server.BaseHTTPRequestHandler):
    server_version = "fx/2.0"

    def _cookie_token(self):
        raw = self.headers.get("Cookie")
        if not raw:
            return None
        try:
            c = SimpleCookie(raw)
            return c[COOKIE].value if COOKIE in c else None
        except Exception:
            return None

    def _serve_index(self, extra_headers=None):
        with open(INDEX, "rb") as fh:
            body = fh.read()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra_headers or []):
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _deny(self):
        self.send_response(403)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(DENY_HTML)))
        self.end_headers()
        self.wfile.write(DENY_HTML)

    def do_GET(self):
        u = urlparse(self.path)
        path = u.path
        q = parse_qs(u.query)
        k = (q.get("k") or [None])[0]

        # token in URL -> set cookie, redirect to clean "/" so token disappears
        if k == TOKEN:
            cookie = f"{COOKIE}={TOKEN}; Max-Age={MAXAGE}; Path=/; Secure; HttpOnly; SameSite=Lax"
            self.send_response(302)
            self.send_header("Location", "/")
            self.send_header("Set-Cookie", cookie)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return

        if self._cookie_token() != TOKEN:
            self._deny()
            return

        if path in ("/", "/index.html"):
            self._serve_index()
            return

        m = re.fullmatch(r"/([jr])/(\d{4}-\d{2}-\d{2})\.json", path)
        if m:
            self._serve_row("judgment" if m.group(1) == "j" else "result", m.group(2))
            return

        self.send_response(404)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _serve_row(self, table, d):
        try:
            con = sqlite3.connect(JDB)
            row = con.execute(f"SELECT json FROM {table} WHERE date=?", (d,)).fetchone()
            con.close()
        except Exception:
            row = None
        if not row:
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        body = row[0].encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_HEAD(self):
        if self._cookie_token() != TOKEN:
            self.send_response(403)
        else:
            self.send_response(200)
        self.end_headers()

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("127.0.0.1", 8090), Handler) as httpd:
        httpd.serve_forever()
