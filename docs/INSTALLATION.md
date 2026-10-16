# INSTALLATION

Deux installations séparées, sur deux machines éventuellement différentes.

| Composant | Machine | Rôle |
|---|---|---|
| `frontend/` | PC **Windows** | l'interface pour les enfants |
| `robot-service/` | **Linux** | le service qui parle au robot |

> Pour apprendre, seul le PC Windows suffit : le service tourne alors en
> **simulation** et peut être lancé sur le PC Windows lui-même.

---

## 1. PC Windows — l'interface

### Prérequis

- **Node.js 20 ou plus** — <https://nodejs.org>
- npm 10 ou plus (fourni avec Node)
- un navigateur récent

### Vérifier Node

Ouvrir une invite de commandes (`cmd`) :

```cmd
node --version
npm --version
```

**Attendu :** `v20.x.x` ou plus.

### Installer

Ouvrir une invite de commandes **dans le dossier du projet** :

```cmd
cd C:\chemin\vers\scratch-robot\frontend
npm install
```

**Attendu :** `added ... packages` et `found 0 vulnerabilities`.

> Cela prend 1 à 3 minutes au premier lancement : ~140 paquets, dont Blockly.

### Erreurs fréquentes

| Message | Cause | Solution |
|---|---|---|
| `'node' n'est pas reconnu...` | Node absent ou PATH non à jour | réinstaller Node, puis **rouvrir** l'invite |
| `npm : impossible de charger le fichier...` | PowerShell bloque les scripts | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| `EACCES` / `EPERM` | antivirus ou manque de droits | désactiver l'antivirus le temps de l'installation, ou relancer en administrateur |
| `ETIMEDOUT` sur le registre npm | proxy / pare-feu | vérifier le proxy, ou `npm config set registry https://registry.npmjs.org/` |
| `Cannot find module 'blockly'` | `npm install` non lancé | refaire `npm install` dans `frontend/` |

---

## 2. Machine Linux — le service

### Prérequis

- **Python 3.10 ou plus**
- Python 3.10 est validé par le projet (`requires-python = ">=3.10"`)

### Vérifier

```bash
python3 --version
```

### Installer

```bash
cd /chemin/vers/scratch-robot/robot-service
python3 -m pip install -e ".[dev]"
```

**Attendu :** `Successfully installed ... go2-service ...`

Le message `[dev]` installe aussi les outils de test (pytest, httpx). Sans eux,
l'application fonctionne mais les tests ne tournent pas.

### Erreurs fréquentes

| Message | Cause | Solution |
|---|---|---|
| `externally-managed-environment` | PEP 668 (Debian/Ubuntu récent) | utiliser un environnement virtuel (ci-dessous) |
| `No matching distribution found` | Python trop ancien | vérifier `python3 --version` |
| `ModuleNotFoundError: go2_service` | mauvaise installation | refaire depuis `robot-service/` |

### Environnement virtuel (recommandé)

```bash
cd /chemin/vers/scratch-robot/robot-service
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

Sous Windows (PowerShell) :

```powershell
cd C:\chemin\vers\scratch-robot\robot-service
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

---

## 3. Lancer l'application

### Terminal 1 — le service

```bash
cd robot-service
python -m go2_service
```

**Attendu :**

```
Service démarré en mode simulation
Uvicorn running on http://127.0.0.1:8765
```

### Terminal 2 — l'interface

```cmd
cd frontend
npm run dev
```

**Attendu :**

```
VITE ready in ...ms
Local: http://localhost:5173/
```

### Ouvrir

<http://localhost:5173>

L'application doit afficher, en haut à droite :

- **Mode simulation**
- **Robot connecté**

Et l'éditeur de blocs doit être visible.

---

## 4. Si l'interface affiche « Robot non connecté »

| Cause probable | Vérification | Solution |
|---|---|---|
| le service n'est pas lancé | `http://127.0.0.1:8765/api/status` doit répondre | lancer le service (étape 3) |
| mauvais port | `shared/safety-limits.json` → `service.port` | l'interface lit la valeur de compilation ; vérifier `VITE_SERVICE_URL` |
| origine non autorisée | l'URL n'est pas dans `service.allowedOrigin` | ouvrir via `http://localhost:5173`, pas via l'adresse IP |

### Changer l'adresse du service

```powershell
cd frontend
$env:VITE_SERVICE_URL="http://192.168.1.50:8765"
npm run dev
```

> Un service exposé sur le réseau local reste **sans authentification**.
> Voir `docs/SAFETY.md`, section « Exposition réseau ».

---

## 5. Tests

### Frontend

```cmd
cd frontend
npm test
```

**Attendu :** `Test Files 4 passed`, `Tests 46 passed`.

```cmd
npm run check
```

**Attendu :** `svelte-check found 0 errors and 0 warnings`.

```cmd
npm run build
```

**Attendu :** `✓ built`, sans avertissement.

### Service

```bash
cd robot-service
python -m pytest -q
```

**Attendu :** `131 passed`.

> Un avertissement `StarletteDeprecationWarning` concernant `httpx` peut
> apparaître : il vient de la bibliothèque tierce `starlette`, pas du projet.

---

## 6. Mode robot réel — installation du SDK Unitree

**À ne faire que lorsque la machine Linux est prête et que la procédure de
`docs/ROBOT_SETUP.md` a été suivie.**

Le SDK Unitree **ne fonctionne pas sur Windows** et **n'est pas validé sous
WSL**.

```bash
sudo apt-get update
sudo apt-get install -y git python3-pip libyaml-cpp-dev

pip3 install cyclonedds
pip3 install git+https://github.com/unitreerobotics/unitree_sdk2_python.git
```

### Réseau

Le robot exige une **interface réseau explicite** :

```bash
ip -br addr          # repérer eth0 ou enp3s0
```

La commande du SDK prend le nom de l'interface en argument :

```bash
python -c "from unitree_sdk2py.core.channel import ChannelFactoryInitialize; ChannelFactoryInitialize(0, 'eth0'); print('OK')"
```

**Ethernet obligatoire.** Le Wi-Fi n'est pas fiable pour le DDS : perte de
paquets et consignes de vitesse manquantes, ce qui est dangereux ici.

### Erreurs fréquentes

| Message | Cause | Solution |
|---|---|---|
| `ModuleNotFoundError: unitree_sdk2py` | SDK non installé | commandes ci-dessus |
| échec de compilation Cython / `cyclonedds` | compilateur absent | `sudo apt-get install -y build-essential python3-dev` |
| connexion qui échoue | mauvaise interface | vérifier `ip -br addr`, utiliser le bon nom |
| robot joignable par `ping` mais pas par le SDK | multicast DDS bloqué | vérifier le pare-feu, le réseau est-il isolé ? |

---

## 7. Désinstallation

```cmd
cd frontend
npm ci --omit=dev   # ou simplement supprimer le dossier node_modules
```

```bash
cd robot-service
python -m pip uninstall go2-service
```

Supprimer `robot-service/.venv` si un environnement virtuel a été créé.

Aucun autre fichier n'est modifié sur le système. L'application n'écrit rien
ailleurs que dans le `localStorage` du navigateur.

---

## 8. Récapitulatif des ports

| Port | Qui l'ouvre | Sens |
|---|---|---|
| 5173 | Vite (interface) | local, développement |
| 8765 | le service robot | local par défaut (`127.0.0.1`) |

Le port 8765 vient de `shared/safety-limits.json` (`service.port`), lu par les
deux côtés. Pour le changer, modifier ce fichier **et** relancer le service.