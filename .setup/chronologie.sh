#!/bin/bash
# Chronologie fine : code d'etat du robot et consigne Move, ligne par ligne.
set -u
LOG=/root/go2/service.log

echo "=== valeurs exactes de error_code ==="
grep -o 'error_code":[0-9]*' "$LOG" | sort | uniq -c

echo
echo "=== chronologie 08:39:58 -> 08:40:08 (le Move refuse) ==="
grep -E '2026-10-20 08:39:5[89]|2026-10-20 08:40:0' "$LOG" \
  | grep -E 'sportmodestate|api_id": 1008|api_id": 1004|go2_service' \
  | sed -E 's/.*(2026-10-20 [0-9:]+).*error_code":([0-9]+).*/\1 etat=\2/; s/.*(2026-10-20 [0-9:]+).*api_id": (1008|1004).*/\1 COMMANDE \2/; s/.*(2026-10-20 [0-9:]+).*(go2_service.*)/\1 \2/' \
  | cut -c1-120 \
  | uniq -f0 | head -60
