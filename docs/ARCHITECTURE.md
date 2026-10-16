# ARCHITECTURE

Ce document décrit le découpage du projet, les contrats entre les couches et
les choix techniques qui les motivent.

---

## 1. Vue d'ensemble

```
go2-scratch/
├─ shared/
│  └─ safety-limits.json      Source UNIQUE des limites de sécurité
├─ frontend/                  Svelte 5 + TypeScript + Blockly (PC Windows)
│  └─ src/
│     ├─ components/          Composants d'interface
│     └─ lib/
│        ├─ robot/            Modèle de commandes, limites, mouvement, validation
│        ├─ blockly/          Définition des blocs, palette, compilation
│        ├─ programs/         Stockage local des missions
│        ├─ api/              Client HTTP / WebSocket
│        └─ stores/           État applicatif
├─ robot-service/             Python 3.10+ / FastAPI (Linux)
│  └─ src/go2_service/
│     ├─ main.py              API HTTP + WebSocket, cycle de vie
│     ├─ execution.py         Moteur d'exécution
│     ├─ validation.py        Validation AUTORITATIVE
│     ├─ safety.py            Chien de garde et bail
│     ├─ config.py            Lecture de shared/safety-limits.json
│     └─ adapters/            base · motion · simulated · unitree
└─ docs/
```

---

## 2. `shared/safety-limits.json`

**Source de vérité unique.** Le fichier est importé tel quel par le frontend
(« TypeScript ») et lu par le service (« Python »). Modifier une limite ne
peut donc pas créer de divergence entre ce que l'interface accepte et ce que
le service autorise.

Contenu :

| Section | Rôle |
|---|---|
| `motion` | Vitesses maximales, distances et angles par pas |
| `timing` | Bornes d'attente, période de contrôle, délai d'arrêt |
| `program` | Nombre d'étapes, répétitions, durée totale, distances cumulées |
| `safety` | Bail, battement, délai de vérification après arrêt |
| `service` | Interface, port, origines autorisées |

Des tests vérifient des **cohérences** entre ces valeurs, pas seulement leur
présence : le battement doit être plus rapide que le bail, le bail doit être
plus court que la durée maximale d'un programme.

---

## 3. Frontend

### 3.1 Couches

```
App.svelte            Assemblage des 4 zones, orchestration
 ├─ TopBar            identité, projet, connexion, mode, aide
 ├─ BlocklyEditor     enveloppe l'éditeur Blockly
 ├─ ControlPanel      vérifier / démarrer / arrêter / progression
 ├─ MissionPanel      créer, sauver, rouvrir, supprimer
 ├─ HelpModal         aide intégrée
 └─ ModeSwitch        bascule simulation / robot réel
```

### 3.2 Modèle de commandes

`lib/robot/commands.ts` définit un **modèle interne** :

```ts
type RobotCommand =
  | { kind: 'move_forward'; distanceCm: number }
  | { kind: 'move_backward'; distanceCm: number }
  | { kind: 'turn_left'; angleDeg: number }
  | { kind: 'turn_right'; angleDeg: number }
  | { kind: 'wait'; seconds: number }
  | { kind: 'stand_up' } | { kind: 'sit_down' } | { kind: 'stop' }
```

**Ce ne sont pas des méthodes du SDK Unitree.** C'est la langue commune entre
l'éditeur et le service. Le service est seul responsable de la traduction.

`parseCommand()` valide la forme de toute donnée reçue ou stockée. Aucune
confiance n'est accordée à l'entrée.

### 3.3 Du bloc à l'instruction

```
 Espace Blockly
      │
      ▼
 compiler.ts          lit la chaîne de blocs, produit RobotCommand[]
      │               (aucune génération de code, pas d'eval)
      ▼
 validate.ts          plages, cumuls, durée, capacités disponibles
      │
      ▼
 api/client.ts ──────▶ HTTP POST /api/execution/start
```

`compiler.ts` **aplatit** les répétitions : un bloc « Répéter 3 fois » devient
trois fois son contenu. Cela rend les cumuls triviaux à contrôler et évite
toute récursion illimitée.

Un bloc non rattaché au programme est signalé, pas ignoré.

### 3.4 Pourquoi Blockly et pas des cartes déplaçables

L'exigence est de vrais blocs emboîtables. `input_statement` permet
d'accrocher des blocs sous un bloc « Répéter » ; `input_value` permet
d'imbriquer des nombres. C'est ce qui rend le modèle réellement Scratch.

---

## 4. Service

### 4.1 Contrat `RobotAdapter`

`adapters/base.py` définit l'interface que le moteur connaît, et **rien
d'autre** :

```python
class RobotAdapter(Protocol):
    name: str
    physical_commands_enabled: bool
    async def connect(self) -> None: ...
    async def disconnect(self) -> None: ...
    async def get_status(self) -> Status: ...
    async def execute_command(self, command, index, should_stop) -> CommandOutcome: ...
    async def request_stop(self) -> None: ...
    def supports(self, capability: Capability) -> bool: ...
```

Le moteur, la sécurité et l'API ne dépendent que de ce contrat. Changer de
version du SDK n'affecte que l'adaptateur.

`get_status()` ne doit **jamais lever** : il retourne
`state=unknown` / `blocked_reason` pour que l'interface puisse afficher un
état inconnu plutôt que planter.

### 4.2 Adapters

| Adaptateur | Rôle | État |
|---|---|---|
| `SimulatedAdapter` | Développement, tests, démonstration | ✅ Opérationnel |
| `UnitreeAdapter` | Pilotage physique | ❌ **Désactivé** |

`SimulatedAdapter` n'a aucun accès au SDK et aucune socket réseau. Un test
vérifie qu'il ne mentionne même pas `unitree` dans ses identifiants.

Il simule volontairement une **dérive** : sans elle, la boucle de contrôle
serait triviale et ne prouverait rien. Il permet aussi d'injecter des pannes :
perte de connexion en cours de mouvement, commande refusée, robot bloqué.

### 4.3 Validation en profondeur

La validation existe à **deux endroits**, volontairement :

| Emplacement | Rôle | Contournable ? |
|---|---|---|
| `frontend/lib/robot/validate.ts` | Retour immédiat à l'enfant | Oui |
| `robot-service/validation.py` | **Autorité** | Non |

Un client modifié reçoit exactement le même refus du service. C'est testé dans
`test_api.py::TestStartValidation`.

### 4.4 Protocole

| Transport | Usage |
|---|---|
| `GET /api/status` | état du robot et du service |
| `POST /api/mode` | bascule simulation / réel |
| `GET /api/settings` | réglages en vigueur + bornes autorisées |
| `POST /api/settings` | applique des réglages (adulte, borné par les plafonds) |
| `POST /api/execution/start` | démarre un programme (renvoie `runId` immédiatement) |
| `POST /api/execution/stop` | arrêt demandé |
| `POST /api/execution/heartbeat` | battement de sécurité (`run_id`) |
| `WS /ws/events` | progression et état (**lecture seule**) |

**Pourquoi le pilotage reste en HTTP.** Le WS est un canal en lecture seule.
Perdre la connexion WS ne doit jamais interrompre la liaison de sécurité, qui
passe par les battements HTTP. Si la liaison de sécurité tombe, le robot
s'arrête — pas le programme.

`start` répond immédiatement et l'exécution tourne en tâche de fond : un
client ne peut pas bloquer l'exécution en gardant sa requête ouverte.

---

## 5. Sécurité — le point critique

### 5.1 Le constat qui dicte l'architecture

Lu dans l'exemple officiel `unitree_sdk2/example/go2/go2_sport_client.cpp` :

```cpp
sport_client.Move(0.3, 0, 0.3);   // consigne de VITESSE
```

`Move()` définit une **consigne persistante**. L'exemple officiel ne fait
**jamais** de `StopMove()` en sortie de boucle. Donc :

> Si le service s'arrête, se fige ou perd le réseau, **le robot peut continuer
> de marcher avec sa dernière vitesse.**

C'est la raison d'être de tout le reste.

### 5.2 Le bail

```
frontend                          service
   │  POST /start                   │
   │ ─────────────────────────────▶ │  démarre le moteur
   │                                 │
   │  POST /heartbeat   toutes les  │
   │  500 ms ──────────────────────▶ │  lease.last_heartbeat = now
   │                                 │
   │  (l'interface se ferme)         │
   │                                 │
   │                            ▲    │  chien de garde : bail expiré
   │                            └────│  → request_stop(SAFETY)
```

- Battement toutes les **500 ms**, bail de **1500 ms**.
- Le chien de garde surveille au tiers du délai.
- Sans battement pendant plus de 1,5 s → arrêt de sécurité.

Le service est **propriétaire** de la liaison. Une coupure réseau, un onglet
fermé, un plantage du frontend : le robot s'arrête.

### 5.3 Arrêt

Le bouton « Arrêter » de l'interface demande l'interruption. Il **ne
garantit pas** l'arrêt physique. C'est le service qui reste responsable.

L'arrêt est demandé à trois niveaux :

1. `StopSignal` — l'instruction en cours le voit et s'interrompt ;
2. `request_stop()` sur l'adaptateur — consigne nulle puis commande d'arrêt ;
3. `emergency_stop()` — à l'arrêt du service et sur erreur non rattrapable.

Le moteur appelle `request_stop()` dans un `finally` : **aucune exécution ne se
termine sans avoir demandé l'arrêt**, même sur exception.

### 5.4 Distinguer « terminé » de « temps écoulé »

`CommandOutcome.outcome` :

| Valeur | Signification |
|---|---|
| `exact` | cible atteinte d'après l'état **mesuré** |
| `timeout` | délai atteint **sans** confirmation mesurée |
| `stopped` | interrompu sur demande |
| `failed` | erreur de l'adaptateur |

`measured_distance_cm` / `measured_angle_deg` ne sont renseignés que si une
valeur a **réellement été lue dans l'état**. L'interface n'affiche « mesuré »
que dans ce cas ; sinon elle affiche « terminé » ou « temps écoulé ».

Un robot qui glisse ou qui bute est donc annoncé honnêtement, pas présenté
comme ayant réussi.

### 5.5 Limites appliquées à deux endroits

1. **Validation du programme** — plages, cumuls, durée, nombre d'étapes.
2. **`assert_speed_within_limits()`** — appelé par chaque adaptateur juste
   avant de publier une consigne. Protection de dernier niveau, indépendante
   de la validation.

### 5.5 bis Réglages d'adulte : plafonds dans le code

L'interface permet de régler 10 limites pédagogiques (vitesse, distance,
durée…). Ce n'est **pas** un levier de sécurité, et cela repose sur trois
dispositions :

**Les plafonds vivent dans le code, pas dans les données.**

```python
@dataclass(frozen=True)
class HardCeilings:
    max_linear_speed: float = 0.30
    max_angular_speed: float = 0.50
    ...
```

`config.HARD_CEILINGS` est figé à l'import. `apply_settings()` refuse tout
champ hors `[plancher, plafond]` **avant** toute écriture : un client modifié
peut ralentir le robot, jamais l'accélérer au-delà de la valeur livrée.

**Les bornes sont fournies par le service.** `GET /api/settings` renvoie
`values` et `bounds`. Le frontend ne les calcule pas — il ne pourrait donc pas
les élargir de son côté.

**`extra="forbid"` sur tous les modèles de requête.**

Ce détail a une histoire. Le frontend envoyait `adultAuthorised` alors que le
modèle attend `adult_authorised`. Sans `extra="forbid"`, Pydantic ignorait
silencieusement le champ, `adult_authorised` valait `False`, et le service
répondait « Seul un adulte peut modifier les réglages » — un message
trompeur, alors que l'adulte avait bel et bien cliqué. Avec `extra="forbid"`,
l'erreur est visible immédiatement, et verrouillée par un test.

Le même piège avait déjà coûté une session avec `runId` / `run_id` sur les
battements de sécurité. D'où la règle : **tout contrat HTTP entre les deux
tiers est verrouillé par un test de forme de payload.**

À la réception d'un changement de réglage, le service incrémente
`settingsRevision`. Le frontend compare avec la révision de sa dernière
vérification : si elles diffèrent, le rapport affiché n'est plus valable et le
programme doit être revérifié.

### 5.6 Mode réel

Trois conditions cumulatives, vérifiées côté service :

1. autorisation explicite d'un adulte ;
2. `physical_commands_enabled == True` sur l'adaptateur ;
3. robot connecté et dans un état permettant le mouvement.

Tant que la campagne physique n'a pas eu lieu, `UnitreeAdapter.
physical_commands_enabled` vaut `False` et le mode réel est **refusé**, même
avec l'autorisation d'un adulte. Testé dans `test_api.py`.

---

## 6. Distance et angle : ce que le SDK permet vraiment

**Vérifié** : le SDK expose `Move(vx, vy, vyaw)` — une **vitesse**. Il
n'existe aucune commande « avancer de N cm » ni « tourner de N degrés ».

Le service procède donc ainsi :

```
1. lire la position et le cap DEPUIS L'ÉTAT MESURÉ (rt/sportmodestate)
2. publier une vitesse pendant une durée nominale, en boucle à ~200 Hz
3. comparer la progression à la cible, tolérance 5 cm / 8°
4. à l'arrivée OU au délai de sécurité → arrêter, et dire ce qui est vrai
```

`adapters/motion.py` contient cette logique. Le délai de sécurité vaut
`durée_nominale × 2,5 + 1 s` : un robot qui glisse ou bute **s'arrête**, il ne
force pas.

Le seuil de fin est un **seuil bas** (`atteint >= cible - tolérance`) et non
`abs(diff) <= tolérance` : avec la seconde formulation, un dépassement
laisserait le robot continuer d'avancer.

---

## 7. Ce qui n'est volontairement pas fait

| Non fait | Pourquoi |
|---|---|
| `eval`, `Function()`, génération de code | exigence ; et inutile avec un modèle de données |
| Exécution de code par les enfants | hors périmètre, dangereux |
| Pilotage bas niveau (`rt/lowcmd`, CRC32, moteurs) | hors périmètre pédagogique ; un test vérifie son absence |
| Saut, flip, acrobaties, marche à l'envers | le robot peut blesser ; hors périmètre |
| Boucle infinie « Répéter pour toujours » | risque de mouvement sans fin ; `maxTotalSteps` et `maxProgramSeconds` bornent |
| Conditions et variables | pour garder une exécution bornée et prévisible |
| Authentification du service | réseau local de confiance ; le durcir reste possible |
| Sérialisation JSON des programmes | une mission = XML Blockly validé à la lecture |

---

## 8. Points d'extension

- **Nouvel adaptateur** : implémenter `RobotAdapter`. Le moteur, la sécurité
  et l'API n'ont pas à changer.
- **Nouvelles capacités** : ajouter à l'`enum Capability`, les déclarer dans
  `supports()`, puis les traduire en bloc. Elles apparaîtront dans la
  validation et dans l'interface sans autre modification.
- **Observations** : remplacer la position estimée par une odométrie réelle
  si un capteur le permet un jour. Le reste de la chaîne est inchangé.