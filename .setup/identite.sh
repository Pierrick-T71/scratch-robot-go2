#!/bin/bash
# Que se trouve-t-il vraiment en 172.16.13.2 ?
IP=${1:-172.16.13.2}

echo "=== banniere et ports ==="
for port in 22 80 443 8080 11514 12000; do
    timeout 2 bash -c "echo > /dev/tcp/$IP/$port" 2>/dev/null \
        && echo "  port $port : OUVERT" || true
done

echo
echo "=== reponse HTTP (descriptif) ==="
/root/go2env311/bin/python - "$IP" <<'PYEOF'
import socket, sys
ip = sys.argv[1]
for port in (80, 443, 8080):
    try:
        s = socket.create_connection((ip, port), timeout=4)
        s.settimeout(4)
        if port == 443:
            s = __import__("ssl", fromlist=["_create_unverified_context"])._create_unverified_context().wrap_socket(s)
        req = f"GET / HTTP/1.1\r\nHost: {ip}\r\nConnection: close\r\n\r\n".encode()
        s.sendall(req)
        data = s.recv(3000)
        texte = data.decode("utf-8", "replace")
        print(f"  --- port {port} ---")
        for ligne in texte.splitlines()[:18]:
            print("   ", ligne[:120])
        s.close()
    except Exception as exc:
        print(f"  --- port {port} : {type(exc).__name__}")
PYEOF

echo
echo "=== identite reseau ==="
/root/go2env311/bin/python - "$IP" <<'PYEOF'
import socket, sys
ip = sys.argv[1]
mac = None
try:
    with open("/proc/net/arp", encoding="utf-8") as f:
        for ligne in f.readlines()[1:]:
            champs = ligne.split()
            if len(champs) >= 4 and champs[0] == ip:
                mac = champs[3]
                break
except Exception:
    pass
print("  adresse MAC :", mac if mac else "inconnue")
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
try:
    nom, alias, ips = socket.gethostbyaddr(ip)
    print("  nom d'hote :", nom, ips)
except Exception:
    print("  nom d'hote : aucun")
PYEOF

echo
echo "=== le robot parle-t-il en DDS sur le bon interface ? ==="
echo "  sous-domaines DDS usuels d'Unitree, ports 7400-7500 :"
timeout 6 tcpdump -i eth0 -nn "portrange 7400-7500 and multicast" 2>/dev/null | head -10
echo "  (rien = personne ne publie en DDS sur ce reseau)"