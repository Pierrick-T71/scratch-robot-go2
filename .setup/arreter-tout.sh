#!/bin/bash
# Arret complet de GO2 Scratch.
echo "=== arret ==="
for motif in "vite preview" "go2_service"; do
    if pkill -f "$motif" 2>/dev/null; then
        echo "  arrete : $motif"
    else
        echo "  rien a arreter : $motif"
    fi
done
sleep 2

echo
echo "=== ports encore occupes ==="
reste=$(ss -tlnp 2>/dev/null | grep -E '8765|5173')
if [ -n "$reste" ]; then
    echo "$reste"
    echo "  -> des processus ecoutent encore"
else
    echo "  ports 8765 et 5173 libres"
fi