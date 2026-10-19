"""Rend le service joignable depuis le poste de l'enseignant.

Deux modifications au fichier partage de securite, visibles et assumees :

 1. `service.host` : 127.0.0.1 -> 0.0.0.0
    Le navigateur du poste doit atteindre le service du conteneur. Ecoute sur
    127.0.0.1 rendait le service invisible de l'exterieur.
    => Le service devient REJOIGNABLE par tout le reseau 172.16.8.0/21, soit
       environ 2000 machines. Il n'a AUCUNE authentification et peut commander
       un robot. Une regle nftables restreint ensuite l'acces a un seul poste.

 2. `allowedOrigin` : ajout de l'adresse de l'interface.
    Le navigateur bloque toute requete vers une origine non listee : sans cela,
    l'interface s'affiche mais ne parle pas au service.
"""

import json
import sys

chemin = sys.argv[1]

with open(chemin, encoding="utf-8") as fichier:
    data = json.load(fichier)

data["service"]["host"] = "0.0.0.0"

nouvelle_origine = "http://172.16.13.41:5173"
origines = data["service"]["allowedOrigin"]
if nouvelle_origine not in origines:
    origines.append(nouvelle_origine)

data["service"]["$comment"] = (
    "Ecoute sur TOUTES les interfaces pour que le navigateur du poste de "
    "l'enseignant atteigne le service depuis le conteneur. Acces restreint "
    "par une regle nftables a un seul poste. Sans authentification, ne "
    "jamais retirer cette restriction : ce service peut commander un robot."
)

with open(chemin, "w", encoding="utf-8") as fichier:
    json.dump(data, fichier, indent=2, ensure_ascii=False)
    fichier.write("\n")

print("  host          :", data["service"]["host"])
print("  allowedOrigin :", ", ".join(data["service"]["allowedOrigin"]))
print("  vitesse max   :", data["motion"]["maxLinearSpeed"], "m/s (inchangee)")
print("  bail          :", data["safety"]["leaseTimeoutMs"], "ms (inchange)")