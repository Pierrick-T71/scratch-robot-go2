# GO2 Scratch

Application éducative de programmation visuelle pour enseigner la logique aux
enfants à partir de 10 ans, en pilotant un robot quadrupède **Unitree Go2**.

Les enfants assemblent des blocs colorés, comme dans Scratch. Le programme est
traduit en instructions typées, validé, puis exécuté par un service
intermédiaire. Le robot ne bouge que si un adulte l'y autorise, dans une zone
dégagée, avec un moyen d'arrêt à portée de main.

---

## ⚠️ État d'avancement — à lire en premier

| Domaine | État |
|---|---|
| Interface Svelte + TypeScript + Blockly en français | ✅ Terminé et testé |
| Moteur d'exécution, validation, limites | ✅ Terminé et testé |
| Adaptateur simulé | ✅ Terminé et testé |
| Service de communication (HTTP + WebSocket) | ✅ Terminé et testé |
| Sécurité (bail, chien de garde, arrêt) | ✅ Terminé et testé |
| **Intégration physique Unitree Go2** | ⚠️ **Partiellement validée** — WebRTC, postures et déplacements courts testés ; contrôle d'obstacles non validé physiquement |

**Le service démarre toujours en simulation.** Le mode réel exige une
connexion WebRTC explicite et une autorisation adulte. Le 22/10/2026, le robot
`172.16.8.11` a été connecté et a exécuté des postures et des déplacements
courts ; le contrôle d'obstacles du service n'a pas encore été validé
physiquement (voir `docs/TESTS.md`).

Voir `docs/ROBOT_SETUP.md` pour la procédure et `docs/SAFETY.md` pour les
consignes.

---

## Fonctionnalités

- **Éditeur Blockly** en français, 4 catégories, 10 blocs emboîtables.
- **Missions** : créer, nommer, enregistrer, rouvrir, supprimer (stockage local).
- **Vérification** avant tout pilotage, avec message clair et emplacement de l'erreur.
- **Exécution** avec progression étape par étape, valeur mesurée affichée quand elle existe.
- **Arrêt immédiat** toujours visible, plus arrêt automatique si l'interface se déconnecte.
- **Arrêt automatique si le robot est soulevé** : les efforts dans les pieds sont surveillés ; le robot s'arrête, relâche ses pattes et se verrouille.
- **Relevage automatique** : si le robot s'est allongé et que son lidar frotte le sol, il se relève tout seul.
- **Contrôle des obstacles** : avant chaque pas, le robot lit la carte du lidar ; s'il n'y a pas la place pour tout le pas, il ne le fait pas et le programme continue. Un obstacle qui apparaît pendant le pas l'arrête.
- **Fenêtre d'obstacle** : le message complet s'affiche au centre de l'écran, avec un bouton **Fermer**.
- **Interrupteur « Sécurité »** : en haut à droite, il coupe ou réactive la vérification de place du **service** (confirmation adulte). L'anti-obstacle interne du Go2 et les autres protections restent actifs.
- **Mode simulation** par défaut, jamais confondu avec le pilotage réel.
- **Plafonds de sécurité intégrés** : le service robot applique directement des limites strictes (vitesse, distance, rotations, durées) définies côté backend sans encombrer l'interface de boutons de configuration superflus.

### Sécurité et plafonds stricts

L'interface est épurée pour les enfants : aucun réglage complexe ni panneau de configuration encombrant. La sécurité est assurée de manière native par le service :

1. **Le service est l'autorité.** Les limites de déplacement, de vitesse et de rotation sont vérifiées et appliquées directement par le backend.
2. **Les plafonds sont gravés dans le code** (`config.HARD_CEILINGS`) :
   - Vitesse maximale : 0,50 m/s
   - Rotation maximale : 1,20 rad/s
   - Distance par déplacement : 40 à 200 cm
   - Rotation par déplacement : 45 à 180°
   - Attente maximale : 3 à 10 s
   - Durée totale du programme : 30 à 120 s
   - Distance totale : 300 à 1500 cm
   - Rotations totales : 900 à 3600°
   - Nombre de pas : 50 à 500
3. **Aucun contournement possible côté client** : tout ordre hors-limites est rejeté avant tout mouvement physique du robot.

---

## Architecture

```
┌─────────────────────────────┐        ┌──────────────────────────────┐
│  frontend/                  │        │  robot-service/             │
│  Svelte 5 + TS + Blockly    │        │  Python 3.10+ / FastAPI      │
│                             │        │                              │
│  • éditeur de blocs         │  HTTP  │  • validation AUTORITATIVE   │
│  • missions (localStorage)  │ ─────▶ │  • moteur d'exécution        │
│  • progression, messages    │        │  • chien de garde + bail     │
│                             │◀────── │  • adaptateur (simulé/réel)  │
│  N'accède JAMAIS au robot   │   WS   │                              │
└─────────────────────────────┘ évenem.└──────────────┬───────────────┘
                                                            │
                                            ┌───────────────▼──────────────┐
                                            │  Robot (uniquement si la     │
                                            │  campagne physique est faite)│
                                            └──────────────────────────────┘
```

**`shared/safety-limits.json`** est lu par le frontend ET par le service :
une seule source de vérité pour les limites de sécurité, aucune dérive possible.

### Pourquoi un service séparé ?

Le SDK Unitree est **Linux uniquement** (C++/CMake, Ubuntu 20.04 ; ou Python
via `unitree_sdk2py`). Il n'est pas compatible Windows et n'est pas validé
sous WSL : le multicast DDS et le binding d'interface physique ne sont pas
fiables.

Le frontend reste donc sur le PC Windows ; le service tourne sur une machine
Linux (ou le PC embarqué du robot). Le service est aussi le **seul** habilité
à décider d'un arrêt : l'interface ne peut pas garantir l'arrêt physique.

---

## Prérequis

### Poste Windows (interface)

- Node.js 20 ou plus (testé avec 24.21)
- npm 10 ou plus
- Navigateur récent (Chrome, Edge, Firefox)

### Machine Linux (service, uniquement pour le mode robot réel)

- Python 3.10 ou plus
- Ubuntu 20.04 ou plus
- Pour le mode réel uniquement : `unitree_sdk2py` + **connexion Ethernet**
  (le Wi-Fi n'est pas fiable pour le DDS)

---

## Installation

```bash
# Interface
cd frontend
npm install

# Service
cd ../robot-service
python -m pip install -e ".[dev]"
```

Détails et dépannage : `docs/INSTALLATION.md`.

---

## Démarrage

**Terminal 1 — le service :**

```bash
cd robot-service
python -m go2_service
```

**Terminal 2 — l'interface :**

```bash
cd frontend
npm run dev
```

Puis ouvrir <http://localhost:5173>.

L'application démarre **en mode simulation** : le robot ne bougera pas.
C'est le comportement attendu.

---

## Tests

```bash
# Frontend — 217 tests unitaires
cd frontend && npm test

# Frontend — vérification de types
cd frontend && npm run check

# Service — 332 tests (unitaires + intégration API)
cd robot-service && python -m pytest -q
```

État vérifié à la livraison : **217 + 332 = 549 tests, tous passants**,
0 erreur de typage, build de production réussi.

Détails et protocole de test physique : `docs/TESTS.md`.

---

## Documentation

| Document | Contenu |
|---|---|
| `docs/INSTALLATION.md` | Installation pas à pas, dépannage |
| `docs/ARCHITECTURE.md` | Découpage détaillé, contrats, flux |
| `docs/ROBOT_SETUP.md` | **Procédure de validation physique du robot** |
| `docs/SAFETY.md` | Risques, limites, procédures d'arrêt |
| `docs/USER_GUIDE.md` | Guide simple pour enfants et animateurs |
| `docs/TESTS.md` | Inventaire des tests et ce qui a été réellement testé |

---

## 📝 Suivi des développements (`compactage.md`)

> [!IMPORTANT]
> **Règle impérative de développement :**
> À chaque fin d'intervention ou de modification de code, vous devez mettre à jour le fichier `compactage.md` à la racine du dépôt en réécrivant par-dessus ce qui a été fait (résumé concis des actions, configurations modifiées et état de validation).

---

## Limites connues

1. **Le robot réel n'a jamais été piloté.** Voir `docs/ROBOT_SETUP.md`.
2. **Aucune commande « avancer de N cm » n'existe dans le SDK.** Le service
   reconstruit la distance par une boucle sur l'état mesuré. La précision
   obtenue n'est pas garantie ; l'interface affiche la valeur réellement
   mesurée, ou « temps écoulé » si la mesure est absente.
3. **Le retour de position du SDK n'est pas une odométrie.** C'est une
   position estimée par le contrôleur : une dérive est possible.
4. **Aucune confirmation mesurée pour les postures.** L'interface affiche
   « terminé », jamais « mesuré », quand il n'y a pas de mesure.
5. **Pas de conditions ni de variables** dans les blocs, volontairement, pour
   garder une exécution bornée et prévisible.
6. **Le service n'est pas authentifié.** Il est conçu pour un réseau local
   de confiance. Ne pas l'exposer sur Internet (voir `docs/SAFETY.md`).

---

## Licence et données

Aucune donnée personnelle n'est collectée, aucun compte n'est demandé aux
enfants, aucun appel vers un service externe. Les missions restent dans le
navigateur (localStorage). Le service ne fait que du réseau local.

Le SDK Unitree est distribué sous licence BSD-3-Clause par Unitree Robotics ;
Blockly sous Apache-2.0.