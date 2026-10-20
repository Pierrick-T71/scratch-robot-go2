#!/bin/bash
# Chronologie complete : etat du robot, commandes, et journal du service.
set -u
LOG=/root/go2/service.log

echo "=== journal du service (adapteteur) ==="
grep 'go2_service' "$LOG" | tail -25 | cut -c1-190

echo
echo "=== dernieres transitions d'etat ==="
grep -o '2026-10-20 [0-9:]*.*error_code":[0-9]*' "$LOG" \
  | sed -E 's/.*(2026-10-20 [0-9:]+).*error_code":([0-9]+).*/\1 etat=\2/' \
  | awk '{ if ($2 != prev) { print; prev = $2 } }' | tail -20

echo
echo "=== dernieres commandes envoyees ==="
grep 'message sent' "$LOG" | grep 'api_id' | tail -12 | grep -o '2026-10-20 [0-9:,]*.*api_id": [0-9]*.*' | cut -c1-160
