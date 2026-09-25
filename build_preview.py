"""Builds preview.html: a self-contained snapshot of the dashboard to share (data inlined, no server)."""
import re
from pathlib import Path

ROOT = Path(__file__).parent

html = (ROOT / "dashboard.html").read_text(encoding="utf-8")
data = (ROOT / "data.js").read_text(encoding="utf-8")

head = re.search(r"<head>(.*?)</head>", html, re.S).group(1)
head = re.sub(r'<meta charset="utf-8">\s*|<meta name="viewport"[^>]*>\s*', "", head)
body = re.search(r"<body>(.*?)</body>", html, re.S).group(1)

clients = (ROOT / "clients.js").read_text(encoding="utf-8")
body = body.replace('<script src="data.js"></script>', f"<script>{data}</script>")
body = body.replace('<script src="clients.js"></script>', f"<script>{clients}</script>")
body = body.replace('const OFFLINE=location.protocol==="file:";', "const OFFLINE=true;")

(ROOT / "preview.html").write_text(head.strip() + "\n" + body.strip() + "\n", encoding="utf-8")
print("preview.html listo")
