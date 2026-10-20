#!/bin/bash
# Chronologie du cas qui MARCHE : le robot etait deja debout.
set -u
LOG=/root/go2/service.log

echo "=== chronologie 08:38:2x -> 08:38:58 ==="
grep -E '2026-10-20 08:38:[2-5]' "$LOG" \
  | grep -E 'sportmodestate|api_id": 1008|api_id": 1004|api_id": 1003|go2_service' \
  | sed -E 's/.*(2026-10-20 [0-9:]+).*error_code":([0-9]+).*/\1 etat=\2/; s/.*(2026-10-20 [0-9:]+).*api_id": (1008|1004|1003).*/\1 COMMANDE \2/; s/.*(2026-10-20 [0-9:]+).*(go2_service.*)/\1 \2/' \
  | cut -c1-110 \
  | awk '!seen[$0]++ || $2 ~ /COMMANDE/ {print}' \
  | head -45
