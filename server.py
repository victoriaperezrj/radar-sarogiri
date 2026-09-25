import json
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import collect
from analyze import analyze

HOST, PORT = "127.0.0.1", 8787
AUTO_REFRESH_MINUTES = 60
ROOT = Path(__file__).parent
refresh_lock = threading.Lock()


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype):
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False), "application/json; charset=utf-8")

    def do_GET(self):
        if self.path in ("/", "/index.html", "/dashboard.html"):
            self._send(200, (ROOT / "dashboard.html").read_bytes(), "text/html; charset=utf-8")
        elif self.path.split("?")[0] in ("/data.js", "/clients.js"):
            f = ROOT / self.path.split("?")[0].lstrip("/")
            self._send(200, f.read_bytes() if f.exists() else b"", "application/javascript; charset=utf-8")
        elif self.path == "/api/trends":
            self._json(analyze())
        else:
            self._send(404, "not found", "text/plain")

    def do_POST(self):
        if self.path != "/api/refresh":
            return self._send(404, "not found", "text/plain")
        if not refresh_lock.acquire(blocking=False):
            return self._json({"error": "Ya se está actualizando"}, 409)
        try:
            report = collect.run()
            print("Actualizado a pedido")
            failures = {k: v for k, v in report.items() if isinstance(v, str)}
            self._json({"ok": True, "failures": failures, **analyze()})
        finally:
            refresh_lock.release()

    def log_message(self, *args):
        pass


def auto_refresh():
    while True:
        if refresh_lock.acquire(blocking=False):
            try:
                print("Buscando tendencias...")
                report = collect.run()
                failed = [k for k, v in report.items() if isinstance(v, str)]
                print("Listo." + (f" Fallaron: {', '.join(failed)}" if failed else ""))
            except Exception as e:
                print(f"Error al actualizar: {e}")
            finally:
                refresh_lock.release()
        threading.Event().wait(AUTO_REFRESH_MINUTES * 60)


if __name__ == "__main__":
    url = f"http://{HOST}:{PORT}"
    print(f"Radar Sarogiri corriendo en {url}")
    if "--open" in sys.argv:
        threading.Timer(1, lambda: webbrowser.open(url)).start()
    print(f"Se actualiza solo cada {AUTO_REFRESH_MINUTES} minutos. No cierres esta ventana.")
    threading.Thread(target=auto_refresh, daemon=True).start()
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
