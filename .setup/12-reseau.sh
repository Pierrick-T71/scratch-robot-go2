#!/bin/bash
# Reseau : rendre le service joignable et autoriser l'origine de l'interface.
#
# DEUX MODIFICATIONS au fichier partage de securite. Elles sont visibles et
# assumees :
#
#  1. service.host : 127.0.0.1 -> 0.0.0.0
#     Le service doit ecouter sur toutes les interfaces, sinon le navigateur
#     de ton PC ne peut pas l'atteindre depuis le conteneur.
#     => le service devient REJOIGNABLE par tout le reseau 172.16.8.0/21.
#        Il n'a aucune authentification. Une regle nftables limite ensuite
#        l'acces a ton seul poste.
#
#  2. allowedOrigin : ajout de http://172.16.13.41:5173
#     Le navigateur interdit les requetes vers une origine non listee.
set -e

FILE=/root/go2/shared/safety-limits.json
PY=/root/go2env311/bin/python

cp "$FILE" "$FILE.avant-modif"

"$PY" - "$FILE" <<'PYEOF'
import json, sys

chemin = sys.argv[1]
with open(chemin, encoding="utf-8") as f:
    data = json.load(f)

data["service"]["host"] = "0.0.0.0"

origine = "http://172.16.13.41:5173"
origines = data["service"]["allowedOrigin"]
if origine not in origins:
    origins.append(origine)

data["service"]["$comment"] = (
    "Ecoute sur TOUTES les interfaces pour que le navigateur du poste de "
    "l'enseignant atteigne le service depuis le conteneur. ACCES RESTREINT "
    "par une regle nftables a un seul poste. Sans authentification, ne jamais "
    "retirer cette restriction : le service peut commander un robot."
)

with open(chemin, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)
    f.write("\n")

print("  host         :", data["service"]["host"])
print("  allowedOrigin:", ", ".join(data["service"]["allowedOrigin"]))
PYEOF

echo
echo "=== redemarrage du service ==="
pkill -f "go2_service" 2>/dev/null || true
sleep 2
cd /root/go2/robot-service
nohup /root/go2env311/bin/python -m go2_service > /root/go2/service.log 2>&1 &
sleep 6
tail -3 /root/go2/service.log
echo
ss -tlnp 2>/dev/null | grep 8765