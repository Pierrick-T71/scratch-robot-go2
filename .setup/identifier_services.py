"""Identifie les services qui tournent sur une machine.

On interroge chaque port HTTP, on lit le titre de la page et l'en-tete
`Server` : c'est ce qui distingue un robot d'un serveur web.
"""

from __future__ import annotations

import re
import socket
import ssl
import sys

IP = sys.argv[1] if len(sys.argv) > 1 else "172.16.13.2"
PORTS = [int(p) for p in sys.argv[2].split(",")] if len(sys.argv) > 2 else [
    80, 443, 2222, 3000, 3001, 3010, 3020, 5050, 8080, 8090,
]


def http(port: int, tls: bool = False) -> None:
    try:
        s = socket.create_connection((IP, port), timeout=5)
        s.settimeout(5)
        if tls:
            contexte = ssl._create_unverified_context()
            s = contexte.wrap_socket(s, server_hostname=IP)
        s.sendall(
            f"GET / HTTP/1.1\r\nHost: {IP}:{port}\r\nConnection: close\r\n"
            "User-Agent: diagnostic\r\n\r\n".encode()
        )
        morceaux = []
        while len(b"".join(morceaux)) < 6000:
            bloc = s.recv(4096)
            if not bloc:
                break
            morceaux.append(bloc)
        s.close()
    except Exception as exc:
        print(f"  {port:5d}  {type(exc).__name__}: {str(exc)[:60]}")
        return

    texte = b"".join(morceaux).decode("utf-8", "replace")
    entete, _, corps = texte.partition("\r\n\r\n")

    serveur = re.search(r"(?im)^server:\s*(.+)$", entete)
    redirection = re.search(r"(?im)^location:\s*(.+)$", entete)
    titre = re.search(r"(?is)<title[^>]*>(.*?)</title>", corps)

    print(f"  {port:5d}  HTTP — serveur={serveur.group(1).strip() if serveur else '?'}")
    if redirection:
        print(f"         redirige vers {redirection.group(1).strip()}")
    if titre:
        print(f"         titre : {titre.group(1).strip()[:110]}")


def ssh(port: int) -> None:
    try:
        s = socket.create_connection((IP, port), timeout=5)
        s.settimeout(5)
        banniere = s.recv(200).decode("ascii", "replace").strip()
        s.close()
        print(f"  {port:5d}  SSH — {banniere[:100]}")
    except Exception as exc:
        print(f"  {port:5d}  {type(exc).__name__}: {str(exc)[:60]}")


print(f"=== services de {IP} ===")
for port in PORTS:
    if port == 2222:
        ssh(port)
    elif port == 443:
        http(port, tls=True)
    else:
        http(port)
print("=== fin ===")
