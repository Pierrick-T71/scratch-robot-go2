#!/bin/bash
# Chronologie du cas qui MARCHE : etat du robot et commandes, 08:39:00 -> 08:39:13
set -u
LOG=/root/go2/service.log

grep -E '2026-10-20 08:39:0[0-9]|2026-10-20 08:39:1[0-3]' "$LOG" \
  | grep -E 'sportmodestate|api_id": 1008|api_id": 1004|api_id": 1003|go2_service' \
  | sed -E 's/.*(2026-10-20 [0-9:]+).*error_code":([0-9]+).*/\1 etat=\2/; s/.*(2026-10-20 [0-9:]+).*api_id": (1008|1004|1003).*/\1 COMMANDE \2/; s/.*(2026-10-20 [0-9:]+).*(go2_service.*)/\1 \2/' \
  | cut -c1-110 \
  | awk '{ if ($2 ~ /COMMANDE/) { print } else if ($2 != prev) { print; prev = $2 } }' \
  | head -50
