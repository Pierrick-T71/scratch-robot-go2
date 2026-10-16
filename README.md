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
| **Intégration physique Unitree Go2** | ❌ **NON VALIDÉE — aucun test sur le robot** |

**Aucune commande n'a été envoyée à un robot réel.** Le robot est piloté par
un **simulateur**. L'adaptateur physique existe et est codé à partir de
l'API officielle lue dans le dépôt Unitree, mais il est **volontairement
désactivé** : le service refuse le mode robot réel tant que la campagne
physique n'a pas eu lieu.

Voir `docs/ROBOT_SETUP.md` pour la procédure et `docs/SAFETY.md` pour les
consignes.

---

## Fonctionnalités

- **Éditeur Blockly** en français, 4 catégories, 10 blocs emboîtables.
- **Missions** : créer, nommer, enregistrer, rouvrir, supprimer (stockage local).
- **Vérification** avant tout pilotage, avec message clair et emplacement de l'erreur.
- **Exécution** avec progression étape par étape, valeur mesurée affichée quand elle existe.
- **Arrêt immédiat** toujours visible, plus arrêt automatique si l'interface se déconnecte.
- **Mode simulation** par défaut, jamais confondu avec le pilotage réel.

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
# Frontend — 46 tests unitaires
cd frontend && npm test

# Frontend — vérification de types
cd frontend && npm run check

# Service — 131 tests (unitaires + intégration API)
cd robot-service && python -m pytest -q
```

État vérifié à la livraison : **46 + 131 = 177 tests, tous passants**,
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