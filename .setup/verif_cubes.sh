#!/bin/bash
# Quelle taille de cube est reellement deployee ?
set -u
/root/go2env311/bin/python - <<'PY'
import re
import urllib.request

page = urllib.request.urlopen("http://127.0.0.1:5173/", timeout=10).read().decode()
nom = re.search(r'assets/(index-[^"]+\.js)', page).group(1)
code = urllib.request.urlopen(f"http://127.0.0.1:5173/assets/{nom}", timeout=30).read().decode()
for m in re.finditer(r"BoxGeometry\(([^)]{0,60})\)", code):
    print("BoxGeometry(", m.group(1)[:60], ")")
PY
