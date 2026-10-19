#!/bin/bash
# Sonde DDS sur les domaines 0 a 3, en unicast vers le robot.
#
# Le script vit sur le conteneur : plus de guillemets a imbriquer depuis
# PowerShell, donc plus de commande cassee.

for domaine in 0 1 2 3; do
    /root/go2env311/bin/python /root/sonde_dds_plage.py "$domaine" 192.168.123.161 eth0 9 20 2>&1 \
        | grep -E '^---|RESULTAT|PREMIER'
done

echo "### sonde terminee"
