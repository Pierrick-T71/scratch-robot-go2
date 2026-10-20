#!/bin/bash
# Repere les codes d'etat du robot (error_code) pendant les fenetres qui
# interessent : le robot est-il pret a marcher ?
set -u
LOG=/root/go2/service.log

echo "=== suite des error_code sur tout le journal ==="
grep -o 'error_code":[0-9]*' "$LOG" | uniq -c

echo
echo "=== pendant le Move refuse (08:40:00 -> 08:40:06) ==="
grep '2026-10-20 08:40:0' "$LOG" | grep sportmodestate | grep -o 'error_code":[0-9]*' | uniq -c

echo
echo "=== pendant le Move qui marche (08:38:2x -> 08:38:5x) ==="
grep '2026-10-20 08:38:[2-5]' "$LOG" | grep sportmodestate | grep -o 'error_code":[0-9]*' | uniq -c
