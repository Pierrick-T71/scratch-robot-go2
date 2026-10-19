"""Que sont les ports 8551 et 9991 du robot ?

8551 se declare « GStreamer RTSP Server ». 9991 est inconnu.

On interroge les deux avec leurs protocoles propres :
  - RTSP : OPTIONS puis DESCRIBE, qui liste les flux video disponibles ;
  - 9991 : tentative de poignee de main WebSocket, puis divers chemins HTTP.

Savoir quel flux video sort et sous quel nom en dit long sur l'appareil.
"""

from __future__ import annotations

import base64
import socket
import sys

IP = sys.argv[1] if len(sys.argv) > 1 else "172.16.8.11"


def dialogue(port: int, requetes: list[bytes], delai: float = 4.0) -> None:
    for etiquette, requete in requetes:
        try:
            s = socket.create_connection((IP, port), timeout=delai)
            s.settimeout(delai)
            s.sendall(requete)
            donnees = b""
            try:
                while len(donnees) < 3000:
                    bloc = s.recv(2048)
                    if not bloc:
                        break
                    donnees += bloc
            except socket.timeout:
                pass
            s.close()
            texte = donnees.decode("utf-8", "replace")
            print(f"  [{etiquette}] {len(donnees)} octets")
            for ligne in texte.splitlines()[:14]:
                print(f"      {ligne[:120]}")
        except Exception as exc:
            print(f"  [{etiquette}] {type(exc).__name__}: {str(exc)[:70]}")
        print()


print("=== RTSP sur 8551 ===")
dialogue(
    8551,
    [
        (
            "OPTIONS",
            b"OPTIONS rtsp://%b RTSP/1.0\r\nCSeq: 1\r\nUser-Agent: diag\r\n\r\n"
            % IP.encode(),
        ),
        (
            "DESCRIBE /",
            b"DESCRIBE rtsp://%b/ RTSP/1.0\r\nCSeq: 2\r\nAccept: application/sdp\r\n"
            b"User-Agent: diag\r\n\r\n" % IP.encode(),
        ),
        (
            "DESCRIBE /stream",
            b"DESCRIBE rtsp://%b/stream RTSP/1.0\r\nCSeq: 3\r\nAccept: application/sdp\r\n"
            b"User-Agent: diag\r\n\r\n" % IP.encode(),
        ),
    ],
)

print("=== 9991 : poignee de main WebSocket ===")
cle = base64.b64encode(b"0123456789abcdef").decode()
dialogue(
    9991,
    [
        (
            "WS /",
            f"GET / HTTP/1.1\r\nHost: {IP}:9991\r\nUpgrade: websocket\r\n"
            f"Connection: Upgrade\r\nSec-WebSocket-Key: {cle}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n".encode(),
        ),
        (
            "GET /api",
            f"GET /api HTTP/1.1\r\nHost: {IP}:9991\r\nConnection: close\r\n\r\n".encode(),
        ),
        (
            "GET /status",
            f"GET /status HTTP/1.1\r\nHost: {IP}:9991\r\nConnection: close\r\n\r\n".encode(),
        ),
    ],
)
