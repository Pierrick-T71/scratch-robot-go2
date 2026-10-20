#!/bin/bash
# Commandes et etats autour du dernier programme « s'asseoir ».
set -u
LOG=/root/go2/service.log

echo "=== journal de l'adaptateur ==="
grep 'go2_service' "$LOG" | tail -20 | cut -c1-190

echo
echo "=== chronologie etat + commandes (20 dernieres transitions) ==="
grep -E 'sportmodestate|api_id": 100[3489]|go2_service' "$LOG" \
  | sed -E 's/.*(2026-10-20 [0-9:]+).*error_code":([0-9]+).*/\1 etat=\2/; s/.*(2026-10-20 [0-9:]+).*api_id": (1008|1004|1003|1009).*/\1 COMMANDE \2/; s/.*(2026-10-20 [0-9:]+).*(go2_service.*)/\1 \2/' \
  | cut -c1-110 \
  | awk '{ if ($2 ~ /COMMANDE/) { print } else if ($2 != prev) { print; prev = $2 } }' \
  | tail -30
