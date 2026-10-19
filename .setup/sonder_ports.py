"""Que repondent les ports 8551 et 9991 du robot ?

Ce sont les deux seuls ports ouverts. Sur un Go2, ils correspondent au
service de flux video et a l'API de commande. On veut savoir lequel est
lequel, et si l'un d'eux donne un etat du robot.
"""

from __future__ import annotations

import socket
import ssl
import sys

IP = sys.argv[1] if len(sys.argv) > 1 else "172.16.8.11"


def tcp_brut(port: int, charge: bytes | None = None) -> None:
    print(f"--- port {port} : lecture passive (5 s) ---")
    try:
        s = socket.create_connection((IP, port), timeout=5)
        s.settimeout(5)
    except Exception as exc:
        print(f"    connexion impossible : {type(exc).__name__}")
        return

    if charge:
        try:
            s.sendall(charge)
        except Exception as exc:
            print(f"    envoi impossible : {type(exc).__name__}")

    try:
        donnees = s.recv(600)
        if donnees:
            texte = donnees.decode("utf-8", "replace")
            if texte.isprintable() or "HTTP" in texte:
                print(f"    recu : {texte[:400]!r}")
            else:
                print(f"    recu {len(donnees)} octets binaires : {donnees[:60].hex()}")
        else:
            print("    connexion ouverte, aucun octet envoye")
    except socket.timeout:
        print("    connexion ouverte, silence pendant 5 s")
    except Exception as exc:
        print(f"    erreur : {type(exc).__name__}")
    finally:
        s.close()


for port in (8551, 9991):
    tcp_brut(port)

print()
for port in (8551, 9991):
    print(f"--- port {port} : requete HTTP ---")
    try:
        s = socket.create_connection((IP, port), timeout=5)
        s.settimeout(5)
        s.sendall(
            f"GET / HTTP/1.1\r\nHost: {IP}:{port}\r\nConnection: close\r\n"
            "User-Agent: curl/8\r\n\r\n".encode()
        )
        donnees = s.recv(1200)
        print("   ", donnees.decode("utf-8", "replace")[:700].replace("\r\n", "\n    "))
        s.close()
    except Exception as exc:
        print(f"    erreur : {type(exc).__name__}: {str(exc)[:80]}")

print()
print("--- HTTPS sur 9991 (certains services Unitree sont en TLS) ---")
try:
    contexte = ssl._create_unverified_context()
    s = socket.create_connection((IP, 9991), timeout=5)
    s = contexte.wrap_socket(s, server_hostname=IP)
    print("    TLS etabli, certificat :", s.getpeercert())
    s.close()
except Exception as exc:
    print(f"    TLS impossible : {type(exc).__name__}: {str(exc)[:100]}")
