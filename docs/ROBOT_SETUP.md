# ROBOT_SETUP — Validation de l'intégration physique

> ## ⚠️ ÉTAT ACTUEL : RIEN N'A ÉTÉ TESTÉ SUR UN ROBOT
>
> **Aucune commande n'a été envoyée à un Unitree Go2.** Tout ce qui suit est
> une **procédure à exécuter**, pas un compte rendu d'essai.
>
> Tant que cette procédure n'est pas faite et ses résultats consignés dans
> la section « Résultats d'essais », l'adaptateur physique reste **désactivé**
> et l'application ne fonctionne qu'en simulation.

---

## 1. Pourquoi une procédure séparée

Le projet est destiné à des enfants. Un pilote défectueux peut faire tomber un
robot de 40 cm de haut sur quelqu'un. On sépare donc strictement :

- **tout ce qui est automatisé** tourne sur le simulateur ;
- **le contrôle physique** se fait une commande à la fois, à la main, dans
  une zone dégagée, avec un adulte et un moyen d'arrêt à portée de main.

Aucune batterie de tests automatisés de mouvements ne doit être lancée.

---

## 2. Prérequis vérifiés par la documentation

| Point | Constat | Source |
|---|---|---|
| Système du SDK C++ | Ubuntu 20.04, CMake ≥ 3.10, gcc 9.4.0 | README `unitree_sdk2` |
| SDK Python | `unitree_sdk2py`, maintenu (dernier push 2026-09-21) | dépôt officiel |
| Windows | **Non supporté** | DDS/CycloneDDS non portable |
| WSL | **Exclu** | multicast DDS et binding d'interface physique non fiables |
| Réseau | `ChannelFactoryInitialize(0, <interface>)` — Ethernet conseillé | exemples officiels |

### API réellement lue dans le code officiel

```python
from unitree_sdk2py.core.channel import ChannelFactoryInitialize
from unitree_sdk2py.go2.sport.sport_client import SportClient

ChannelFactoryInitialize(0, "eth0")   # interface réseau OBLIGATOIRE
client = SportClient()
client.SetTimeout(10.0)
client.Init()
```

| Méthode | Vérifiée dans | Retenu pour ce projet |
|---|---|---|
| `Move(vx, vy, vyaw)` | C++ et Python | ✅ déplacement |
| `StopMove()` | C++ et Python | ✅ arrêt |
| `StandUp()` | C++ et Python | ✅ se lever |
| `StandDown()` | C++ et Python | ✅ s'asseoir (repli) |
| `Hello()`, `Stretch()` | Python | ✅ saluer, s'étirer |
| `Damp()` | C++ et Python | ✅ se coucher, et relâcher les pattes en sécurité de portage |
| `BalanceStand()`, `RecoveryStand()` | C++ et Python | ✅ mais inutilisés ici |
| `HandStand`, `LeftFlip`, `BackFlip`, `FreeBound`, `FreeAvoid`, `WalkUpright`, `CrossStep`, `FreeJump` | Python | ❌ **écartés** : acrobaties dangereuses |
| `FreeWalk` | Python | ❌ **écarté** : le robot le refuse (`3203`) dans l'espace de commandes normal ; il faudrait basculer en mode MCF (`rt/api/motion_switcher/request`), non documenté |
| `Sit()`, `RiseSit()` | **C++ seulement** | ❓ **à vérifier** en Python |
| `SwitchGait()`, `Euler()`, `BodyHeight()` | C++ | ❌ hors périmètre pédagogique |

État mesuré : sujet DDS `rt/sportmodestate`, type `SportModeState_`,
champs `position()[0..2]` et `imu_state().rpy()[2]`.

### Le risque documenté

L'exemple officiel boucle sur `Move()` à `dt = 0.005` s (200 Hz) et **ne fait
jamais de `StopMove()` en sortie de boucle**. `Move()` pose une **consigne
persistante**.

> Si le service s'arrête ou perd le réseau, le robot peut continuer de marcher.

C'est la raison d'être du bail de sécurité (`docs/SAFETY.md`).

### Une consigne de mouvement relève le robot (mesuré)

Constat fait sur le robot réel, via le canal WebRTC : **une commande `Move`
envoyée à un robot assis le remet debout.** Le robot passe en mode « sport »
dès qu'il reçoit une consigne de vitesse, même nulle.

Pire : **`StopMove` le relève aussi.** Une mesure faite le 20/10/2026, en
lisant la hauteur du robot dans l'état publié par le SDK (0,32 m debout,
0,22 m assis) :

| Phase | Hauteur observée | Lecture |
|---|---|---|
| robot assis, 30 s sans aucune commande | 0,222 m, stable | le robot **reste** assis tout seul |
| programme « s'asseoir », robot déjà assis | 0,222 → 0,308 → 0,328 m | il se relève, mais **la posture demandée est refusée** : il reste debout |

Le refus venait de l'ordre des commandes : le robot recevait « se relever »
puis « s'asseoir » 0,6 s plus tard, **pendant** sa transition de posture. Le
Go2 met 2 à 3 secondes à se relever et refuse toute commande envoyée
pendant ce temps.

Règles retenues dans l'adaptateur (`adapters/webrtc.py`) :

- `prepare_run()` : avant le premier ordre d'un programme, on **vérifie** que
  le robot est debout — d'après la **hauteur mesurée** (comparée à la plus
  haute hauteur vue depuis la connexion), et d'après le dernier ordre de
  posture quand la mesure manque. S'il ne l'est pas, `StandUp` ;
- après un `StandUp` ou un `Sit`, on **attend que la hauteur cesse de
  changer** avant la commande suivante (`_attendre_stable()`) ;
- une posture **refusée** est réessayée **une fois**, après stabilisation ;
- une posture **acquittée mais pas tenue** (le robot s'est relevé) est
  réessayée elle aussi ;
- `request_stop()` : si le robot est assis, **rien** n'est envoyé. `Move` et
  `StopMove` le relèvent tous les deux ; un robot assis ne se déplace pas,
  il n'y a donc aucune consigne à annuler ;
- `_do_move()` : un déplacement demandé alors que le robot est assis commence
  par un `StandUp` explicite.

### « S'asseoir » ne tenait pas : l'acquittement arrive trop tard (21/10/2026)

Constat sur le robot réel : le programme « s'asseoir » revenait avec
« temps écoulé (non mesuré) », et le chien **se relevait aussitôt**.

Chronologie mesurée (journal du service) :

| Instant | Événement |
|---|---|
| 12:56:28,4 | commande `Sit` envoyée |
| 12:56:31,5 | délai de 3 s dépassé : le service abandonne la commande |
| 12:56:32,4 | le robot publie `1006` (début de transition) |
| 12:56:32,6 | le robot publie `1007` — **il est bien assis** |
| 12:56:32,6 | `2005` puis `100` : l'arrêt de fin de programme le relève |

Deux causes, corrigées :

1. **Le délai d'acquittement de 3 s était trop court.** Le robot acquitte
   « s'asseoir » après 2 s, parfois plus de 3 s (il attend la fin de son
   cycle de marche). Une commande de posture a désormais son propre délai
   (`POSTURE_TIMEOUT_S = 8 s`).
2. **L'acquittement peut se perdre alors que le robot obéit.** Dans ce cas,
   c'est l'**état publié par le robot** qui fait foi : `1007` = assis. Le
   service attend donc la posture publiée (`_attendre_posture()`) au lieu de
   conclure à un échec. Comme la posture est alors vraiment tenue, l'arrêt
   de fin de programme n'envoie rien (`_est_assis()` est vrai) et le robot
   **reste assis**.

Vérifié le 21/10/2026 sur le robot réel : programme « s'asseoir » → `1006`
puis `1007`, hauteur 0,31 m → 0,22 m, et **20 s plus tard le chien est
toujours assis**. Le programme suivant le relève : `1002` → `100`, sans
aucun arrêt de sécurité.

Le code d'état est désormais journalisé à chaque changement
(`Etat du robot : 1007`) : c'est la trace qui a permis de comprendre la
chrono ci-dessus.

### Durée réelle et angle réel (corrigé le 21/10/2026)

Trois causes distinctes faisaient qu'« 1 seconde » durait 5,7 s et que 90°
demandés donnaient 139° :

1. **Le SDK journalisait chaque message sur le logger racine**, au niveau
   INFO : 474 Mo en 2 h. L'écriture synchrone saturait la boucle asyncio, et
   l'état lu par le service avait **4,12 s de retard** (médiane). Le point
   d'entrée coupe désormais ce flot (`_couper_le_flot_du_sdk()` dans
   `__main__.main()`), tout en gardant `go2_service` à INFO.
2. **Le test « robot prêt » comparait un entier à un ensemble.** Dans
   `_do_move`, `self._code_etat != self.ETAT_PRET` était toujours vrai : chaque
   déplacement attendait donc la stabilisation de la hauteur, jusqu'à 6 s,
   avant d'envoyer sa première consigne. Le test correct est
   `code not in ETAT_PRET`.
3. **La boucle comptait ses tours au lieu de lire l'horloge.** `ecoule += 0.05`
   dérive dès qu'un `await` dure plus de 50 ms. Elle utilise maintenant
   `time.monotonic()`.

Sémantique retenue, différente pour les deux mouvements :

| Mouvement | Cible | Commande |
|---|---|---|
| Avancer / reculer / côté | **durée** demandée | `Move(vx, vy, 0)` tenu exactement `duration_s` à l'horloge murale, puis `StopMove` |
| Tourner | **angle** demandé | servo proportionnel sur le cap mesuré (`imu.rpy[2]` déroulé), arrêt dans la bande morte |

Coefficients du servo de cap (`adapters/motion.py`) :

- bande morte : **1°** — sous cet écart, on arrête ;
- gain : **4 /s** — vitesse = 4 × écart en radians, bornée à 0,5 rad/s ;
- plancher : **0,10 rad/s** (5,7°/s) — le servo ne cale pas à quelques degrés ;
- délai de sécurité : durée nominale à vitesse maximale × 2,5 + 1 s, plus 2 s
  de freinage.

La rotation est **refusée** si le cap n'est pas mesuré (ou plus mesuré depuis
plus de 2 s) : tourner à l'aveugle est exactement ce qui produisait 139°.

### La clé AES-128 du robot

Le firmware récent (Go2 ≥ 1.1.15) refuse d'ouvrir le canal sans la clé
AES-128 de la machine. Elle vit **hors du dépôt**, dans
`/root/go2/robot.env` (droits 600) :

```
GO2_ROBOT_AES_KEY=…
```

Elle est lue par le service dans deux endroits, dans cet ordre :

1. la variable d'environnement `GO2_ROBOT_AES_KEY` ;
2. le fichier `GO2_ROBOT_ENV_FILE` (par défaut `/root/go2/robot.env`).

Ce doublet n'est pas un caprice : la machine a été redémarrée, et le
service relancé par une **autre copie** du script de démarrage, qui ne
chargeait pas le fichier. Le branchement était alors refusé avec « la clé
AES-128 du robot est absente ». Comme le service sait désormais lire le
fichier lui-même, plus aucun script de démarrage ne peut lui retirer la clé.

Les deux copies du script (`/usr/local/bin/demarrer.sh` et
`/root/demarrer.sh`) chargent le fichier, et le déploiement les met à jour.

### Le code d'état du robot : 100, 1002, 1006, 1007

Le SDK publie un `error_code` dans l'état du robot. Relevé sur la machine le
20/10/2026 :

| Code | Signification observée |
|---|---|
| `100` | debout, au repos ou en marche : le robot **suit** les consignes |
| `1002` | **transition de posture** (il se relève) |
| `1006` | début de transition (vers la position assise) |
| `1007` | assis, stable |
| `2005` | position assise en cours, puis retour debout |

Deux conséquences, chacune mesurée :

1. **Pendant une transition, le robot ignore les consignes `Move`.** Et les
   lui envoyer empêche *même* la transition de se terminer : le robot peut
   rester planté en `1002` pendant des dizaines de secondes. Il ne suffit
   donc pas d'attendre : il ne faut rien envoyer.
2. **Pour sortir de la transition, il faut reprendre la main sur la
   vitesse.** Une consigne de vitesse **nulle** (`Move(0, 0, 0)` suivie de
   `StopMove`) fait passer le robot de `1002` à `100` en une seconde environ.
   Sans elle, toutes les consignes de mouvement du programme restent
   ignorées.

D'où la règle : après un `StandUp`, on attend la fin du redressement, on
envoie la consigne **nulle**, et on n'envoie plus rien tant que le robot ne
publie pas `100`.

Journal des commandes réellement envoyées (pour relecture après coup) :

```
2026-10-20 08:32:15,330  Robot non debout (posture Posture.SIT, hauteur 0.222704) : remise sur quatre pattes.
2026-10-20 08:32:15,330  Commande envoyee au robot : StandUp
2026-10-20 08:32:17,178  Commande envoyee au robot : Sit
```

Aucune commande ensuite : le robot reste assis. La hauteur est repassée de
0,308 m (debout) à 0,223 m (assis), et y est restée.

Et le même programme, cette fois avec « avancer » : le robot se relève, la
consigne nulle part, le code d'état repasse à `100`, et le robot parcourt
**58 cm** pour 2 s demandées à 0,3 m/s (60 cm attendues).

### La caméra du robot

Le SDK `unitree_webrtc_connect` expose un canal vidéo :

- `conn.video.switchVideoChannel(True)` demande au robot d'envoyer sa
  caméra ;
- `conn.video.add_track_callback(...)` reçoit la piste vidéo.

Mesuré le 20/10/2026 : le robot envoie du **1280x720**, en H.264. Le service
relaie ces images vers le navigateur au format **MJPEG**
(`/api/robot/camera`) ; la clé AES ne quitte jamais la machine qui parle au
robot. En l'absence de caméra (simulation, robot non branché), la route
répond `503` et l'interface montre la vue 3D du robot.

### Le capteur lidar (la vue « voxels »)

Le lidar du Go2 publie sa carte sur `rt/utlidar/voxel_map_compressed`. Le
SDK la décode en un **maillage** : `positions` sont les sommets, exprimés
comme des **indices dans la grille** (128×128×38, à 5 cm), et `origin` /
`resolution` placent la grille dans le repère du robot.

Deux détails mesurés le 20/10/2026 :

- le lidar ne publie sa carte que lorsque le robot est **debout** ;
- la commande d'allumage est `rt/utlidar/switch` ; sans elle, seuls l'état
  du capteur (`rt/utlidar/lidar_state`) arrive, sans les points.

Le service renvoie le volume en **base64** (les cases occupées sont trois
octets chacune) sur `/api/robot/lidar`, avec la **pose du robot** : sa place
dans la carte et son **cap**.

Cette pose est décisive : la carte est exprimée dans le repère « odom » (celui
du monde), **pas** dans celui du robot. Le robot n'est donc pas forcément au
centre de la grille, et il ne regarde pas forcément dans l'axe x. C'est
`rt/utlidar/robot_pose` qui donne sa place et son cap — sans elle, le chien
serait posé au milieu de la carte en regardant n'importe où.

L'interface en fait la vue **3D** de l'application du constructeur : un volume
de petits cubes (une case = 5 cm), colorés selon la hauteur (vert au sol,
jaune et orange plus haut, violet en haut), la grille du sol, et le modèle
3D du chien posé à la **place réelle** du robot et tourné vers son **cap
réel** — le lidar est bien devant lui, et ce qui est devant dans la carte
est devant lui.

La même scène sert de vue par défaut, **sans les cubes** : le robot au
milieu de la grille sombre. Le bouton lidar ajoute la carte ; dans cette
vue on peut tourner autour du robot, alors que la vue par défaut reste
passive.

Le modèle vient de `public/model/go2.glb` (modèle public de Sketchfab,
CC-BY-4.0, fourni dans `robot-toutou`). La hiérarchie des pattes a été
conservée : 94 nœuds, 20 maillages, 7,3 Mo après simplification
(`gltfpack -kn -km -noq -si 0.3 -se 0.02`). Il ne contient ni squelette ni
clip d'animation : le rig est construit au chargement (groupes
hanche → genou → cheville), et la marche est une animation procédurale
lancée quand un bloc de déplacement tourne.

⚠️ Trois pièges de three.js, appris à l'usage :
- la sphère englobante d'un maillage instancié est calculée **une fois** : si
  elle l'est quand il n'y a encore aucun cube, le maillage reste hors champ ;
- les couleurs sont **par instance** (le volume est coloré selon la hauteur),
  pas par sommet : demander des couleurs par sommet rend les cubes noirs ;
- la géométrie doit être créée **à la taille d'une case** : la redimensionner
  plus tard ne prend pas.

Et la caméra n'est posée **qu'une fois** : la replacer à chaque nouvelle carte
renverrait l'utilisateur à sa position de départ à chaque balayage.

Le rendu est allégé : 12 000 cubes au maximum, et un pixel ratio plafonné à
1,5 — au-delà, un rendu logiciel ne suit plus.

#### La même carte sert à éviter les murs

Depuis le 22/10/2026, la carte n'est plus seulement une vue : elle décide si
une translation a la place de se faire.

- Le service ne garde que les voxels situés entre **0,25 m et 1,60 m** au-dessus
  d'un **niveau de sol robuste**, estimé par la **médiane des hauteurs**.
  Le minimum absolu est volontairement écarté : le 22/10/2026, un unique voxel
  aberrant à -0,275 m sous le plancher avait fait passer tout le sol pour un
  mur et refusé une avance de 1 s alors que la voie était libre sur 1,45 m.
  Un percentile bas restait insuffisant : le sol s'étale sur ~0,35 m de haut
  et sa couche supérieure réapparaissait comme obstacle (mesuré à 0,025 m
  avec un 10e percentile à -0,225 m). La médiane donne le niveau du sol ;
  les couches basses sont ensuite écartées par la marge de 0,25 m.
  Le sol cartographié, les pattes et le plafond sont donc écartés.
- Il regarde un couloir de **± 0,30 m** autour de la direction du pas et prend
  la case la plus proche. La distance nécessaire vaut
  `0,40 m + vitesse × durée + 0,05 m` (0,25 m au lieu de 0,40 m pour un pas
  latéral, et un couloir de ± 0,45 m car le corps est en travers).
- Si la place manque, l'action n'est **pas** faite (elle n'est pas raccourcie)
  et le programme continue. Pendant le pas, la mesure est refaite à 10 Hz ;
  un obstacle qui apparaît arrête le robot.
- Sans carte ou sans pose de moins de 2 s, aucune décision n'est prise :
  `clearance_m()` renvoie `None`. On ne prouve pas un mur avec une carte
  absente.

Le 21/10/2026, la carte 2D comptait environ **2 100 cases** : elle contient
très probablement le sol, d'où le filtre de hauteur. **À vérifier sur le robot
réel** lors de la prochaine session :

1. le chien ne doit pas se voir lui-même (aucun cube sur ses pattes ni sur son
   dos) ; s'il se voit, exclure son empreinte dans `obstacles.py` ;
2. le niveau de sol estimé (médiane) doit rester le sol, même en présence
   d'un voxel aberrant sous le plancher ou d'un sol épais ;
3. comparer la distance annoncée (message « il reste X m libres ») à une mesure
   au mètre ruban, robot cap vers un mur ;
4. vérifier qu'une avance de 1 s passe devant un mur à 1 m, et qu'une avance de
   5 s est refusée.

### Les gestes du corps

Quatre gestes, tous des commandes officielles du SDK, sont exposés à l'enfant :

| Bloc | Commande | Effet |
|---|---|---|
| « Saluer » | `Hello` (1016) | le robot salue |
| « S’étirer » | `Stretch` (1017) | le robot s'étire |
| « Faire un cœur » | `FingerHeart` (1036) | le robot fait un cœur avec ses pattes avant |
| « Faire un saut » | `FrontPounce` (1032) | le robot s'accroupit et pousse vers l'avant |

Ces gestes sont distincts des postures : le service refuse tout geste qu'il ne
sait pas exécuter. `CrossStep` (« pas croisé ») reste volontairement absent :
ce n'est pas une action unique mais un mode de marche, et il figure dans les
acrobaties écartées par `docs/SAFETY.md`.

`Hello` et `Stretch` sont exposés par le SDK et validés par les tests et la
simulation ; ils n'ont pas encore été exécutés sur le robot réel dans ce
projet.

### S'allonger et donner un coup de patte

Deux autres actions, elles aussi officielles du SDK :

| Bloc | Commande | Effet mesuré |
|---|---|---|
| « Se coucher » | `Damp` (1001) | le corps passe de 0,32 m à **0,05 m** : allongé par terre, et il y reste |
| « Donner un coup de patte » | `FrontPounce` (1032) | le robot s'accroupit (0,18 m) et pousse très fort, vers l'avant |

### Le robot s'allonge à la fin d'un programme : les gestes avalent la commande

Constat du 21/10/2026 : un programme « faire un cœur » puis « se coucher »
laissait le chien **debout**. Trois causes, corrigées :

1. **Le geste acquittait 6,5 s plus tard.** Le service attendait 3 s,
   abandonnait, et envoyait « se coucher » **pendant que le robot faisait
   encore son geste** : la commande était alors avalée. Les gestes ont
   désormais le même délai que les postures (8 s).
2. **« Se coucher » n'était pas vérifié.** La commande partait, sans qu'on
   regarde si le robot s'était réellement allongé. C'est désormais vérifié
   sur l'**état publié** (`1001`), et la commande est renvoyée une fois si
   le robot n'a pas obéi.
3. **L'arrêt de fin de programme relevait le chien.** Pendant la transition
   vers la position allongée (`1006`), le service envoyait quand même
   `Move(0)` + `StopMove` — et sur un Go2, `Move` relève le robot. Pendant
   une transition de posture, **aucune** consigne de vitesse n'est envoyée.

Le « se coucher » a aussi été retiré des postures « non vérifiées » : il
est mesuré sur le robot réel (le corps passe de 0,32 m à 0,05 m, et le
robot publie `1001`).

### L'état du lidar (`rt/utlidar/lidar_state`)

Le message porte l'état de la fenêtre tournante du lidar :

| Champ | Signification (mesurée le 21/10/2026) |
|---|---|
| `error_state` | 0 en toutes circonstances dans nos essais, y compris allongé |
| `dirty_percentage` | **0 à 8 %** debout, **61 à 70 %** allongé par terre |
| `sys_rotation_speed` | rotation demandée, ≈ 12917 |
| `com_rotation_speed` | rotation réelle, ≈ 261.8 (ratio ≈ 0,0203) |
| `imu_rpy` | attitude de la **tête** du lidar : elle tourne, ce n'est pas l'assiette du robot |

⚠️ **`dirty_percentage` n'est PAS un indice de blocage.** Il monte à 63 %
quand le chien s'allonge, alors que son lidar tourne librement. La
première version du relevage automatique s'appuyait dessus : le chien se
relevait à chaque « se coucher ». C'est faux, et le critère a été remplacé
par la **rotation réelle**.

Le signal juste, c'est la **rotation réelle** (`com_rotation_speed`) :
quand la fenêtre frotte contre le sol, le contrôleur du lidar change de
régime et la rotation s'écarte de sa valeur normale. Mesures du 21/10/2026
(ratio = rotation réelle / rotation demandée) :

| Situation | ratio | écart à la médiane |
|---|---|---|
| normal, debout ou allongé | 0,0202 – 0,0203 | ±1 % |
| pendant un relèvement | 0,0182 | −10 % |
| **lidar bloqué (14:14:44)** | **0,0334** | **+64 %** |
| **lidar bloqué (13:55:59)** | **0,0114** | **−44 %** |

⚠️ **Le blocage se manifeste dans les deux sens.** La première version ne
regardait que la baisse : elle a vu le blocage de 13:55, mais laissé passer
celui de 14:14 (rotation en hausse) — le chien est resté allongé, le lidar
bloqué. Le critère est donc un **écart** de plus de **25 %** dans les deux
sens.

Le seuil retenu est donc **25 % d'écart** autour de la **médiane** des
60 dernières rotations. La médiane, et non le maximum : une mesure anormale
(0,0729, relevée pendant une pose) ferait otherwise passer l'échelle de
3,6×, et tout le reste de la session semblerait « bloqué » — c'est ce qui
s'est passé, et le chien se relevait à chaque « se coucher ».

Et **seules les mesures normales** entrent dans l'historique : sinon un
blocage durable décalerait la référence, et le détecteur s'éteindrait de
lui-même au bout de quelques secondes.

Le premier vrai blocage a été observé le 21/10/2026 : le chien s'est relevé
tout seul 2,4 s après le blocage (confirmation d'une seconde + commande).
Le second (14:14) n'a **pas** été détecté avant la correction ci-dessus.
Deux échantillons ne prouvent pas la marge : il faut en observer d'autres.

### Le robot ne saute pas (pour l'instant)

Les cinq commandes de saut du SDK ont été essayées et mesurées
(`FrontJump`, `FrontPounce`, `Bound`, `FreeJump`, `FreeBound`).

Le signal qui tranche est **l'effort dans les pieds** (`foot_force` de l'état
bas) : zéro signifie que le pied ne touche plus le sol.

| Commande | Effort aux pieds | Hauteur estimée | Verdict |
|---|---|---|---|
| `FrontJump` | 274 (constant, comme debout) | 0,114 → 0,321 m | accroupi et pousse |
| `FrontPounce` | 274 (constant) | 0,180 → 0,522 m | accroupi et pousse plus fort |
| `Bound` | 274 (constant) | 0,301 → 0,308 m | refusée / sans effet |
| `FreeJump`, `FreeBound` | 274 (constant) | 0,309 → 0,311 m | sans effet |

**Les pieds ne déchargent jamais** : le robot garde toujours un pied au sol.

Mesure complémentaire du 21/10/2026, robot debout au repos : `[86, 97, 86,
89]`, puis `[86, 101, 85, 88]`, soit une somme de **358 à 360**. Le seuil de
portage à 60 reste donc très en dessous d'un appui normal.
Le pic d'accélération verticale (31 m/s², soit 3 g) montre une poussée
violente, mais le robot ne décolle pas.

⚠️ Piège à connaître : `body_height` est une **consigne** envoyée au
contrôleur, pas une mesure ; l'odométrie (`position[2]`) est une
*estimation* qui s'emballe pendant un mouvement violent. Seuls les efforts
dans les pieds disent si le robot est en l'air.

Ces efforts servent désormais à la protection de portage : une somme sous 60
pendant que le robot est debout déclenche `Move(0)`, `StopMove`, puis `Damp`,
et un verrouillage. `Damp` relâche les pattes pour qu'elles cessent de chercher
un équilibre dans les mains de la personne qui porte le robot. Voir
`docs/SAFETY.md`, section « Détection de portage ».

### La commande qui manque peut-être : parler en vitesse

L'application officielle envoie une consigne de vitesse **en continu**, même
joystick centré. Le robot reste alors dans l'état « en mouvement » (code
`100`), et c'est dans cet état qu'il exécute les commandes de corps.

Le service fait maintenant de même pendant un geste (`_flux_vitesse`) :
une consigne de vitesse **nulle**, rafraîchie 5 fois par seconde. Le robot ne
bouge pas, il reste à l'écoute.

C'est très probablement là que se trouve la différence entre « le robot
saute » et « le robot donne un coup de patte » : cela dépendait de l'état
dans lequel le robot se trouvait quand la commande arrivait.

### Les codes d'état du robot

Relevés sur la machine, dans l'état `rt/lf/sportmodestate` :

| Code | Signification |
|---|---|
| `1013` | debout et immobile — l'état normal au repos |
| `100` | en mouvement (le client envoie une vitesse) |
| `1002` | transition de posture (il se relève) |
| `1006` | transition vers la position assise |
| `1007` | assis |
| `1001` | allongé par terre (après un `Damp`) |
| `1009` | après un coup de patte |

**C'est cet état, et non la hauteur, qui fait foi.** L'odométrie
(`position[2]`) est une *estimation* : pendant un mouvement violent elle
s'emballe (0,52 m mesurés pendant un bond, pour un robot de 0,32 m). Une
fois cette hauteur aberrante retenue comme référence, le service croyait que
le robot ne pouvait plus être debout : il redemandait `StandUp` sans fin, et
le saut partait dans le chaos. D'où la règle : la référence de hauteur n'est
mise à jour que sur les messages où le robot dit qu'il est debout.

Le service attend `1013` **ou** `100` avant d'agir. Attendre `100` seul
faisait perdre 12 secondes à chaque programme, parce que le robot immobile
publie `1013`.

Une consigne de posture est **vérifiée** après coup, sur l'état publié par le
robot : s'il ne tient pas la posture demandée, la commande est renvoyée une
fois, et l'échec est annoncé à l'enfant plutôt que silencieux.

---

## 3. À VÉRIFIER AVANT TOUT (inconnues assumées)

Ces points sont **inconnus**, pas « probablement bons ». Les vérifier :

| # | Question | Comment |
|---|---|---|
| 1 | Modèle exact : Go2 **Pro** ? Quelle version matérielle ? | étiquette sous le robot |
| 2 | Version du firmware | application officielle Unitree / `unitree_sdk2` |
| 3 | Options installées (LiDAR, Follow-me, carte SD ?) | inspection |
| 4 | Version installée de `unitree_sdk2py` | `pip show unitree_sdk2py` |
| 5 | Signature **réelle** de `SportClient.Move` (ordre vx/vy/vyaw) | `python -c "import inspect; from unitree_sdk2py.go2.sport.sport_client import SportClient; print(inspect.signature(SportClient.Move))"` |
| 6 | `Sit()` / `RiseSit()` existent-elles en Python ? | `dir(SportClient)` |
| 7 | Comportement **réel** de `StopMove()` : arrêt net ou amorti ? Délai ? | essai §5 |
| 8 | `Damp()` est-il l'arrêt le plus sûr ? | essai §6 — **utilisé pour la sécurité de portage (relâcher les pattes), jamais testé physiquement** |
| 9 | Signification du code d'erreur retourné par `Move()` | essai §7 |
| 10 | Fiabilité de `position()` comme retour | comparaison §8 |
| 11 | Fréquence de publication acceptée | essai §9 |
| 12 | Interface réseau : `ip addr` montre `eth0` ? | `ip -br addr` |
| 13 | La télécommande officielle et l'app Unitree ne rentrent-elles pas en conflit ? | essai §10 |
| 14 | Les licences/options autorisent-elles le contrôle programmatique ? | documentation Unitree |
| 15 | **Que vaut `com_rotation_speed` quand le lidar frotte le sol ?** | −44 % (13:55) ou +64 % (14:14) par rapport à la médiane — **à confirmer sur d'autres blocages** |

---

## 4. Installation sur la machine Linux

Sur le PC embarqué du robot, ou un PC Linux dédié sur le même réseau.

```bash
# Dépendances système (Ubuntu 20.04 ou plus)
sudo apt-get update
sudo apt-get install -y git python3-pip libyaml-cpp-dev

# SDK Unitree Python
pip3 install cyclonedds
pip3 install git+https://github.com/unitreerobotics/unitree_sdk2_python.git

# Service du projet
cd go2-scratch/robot-service
python3 -m pip install -e ".[dev]"

# Lancement en simulation sur cette machine (étape 1 de la campagne)
python3 -m go2_service
```

> ⚠️ Si `pip install` échoue sur le SDK : c'est un signal que la machine n'est
> pas un environnement valide. **Ne pas essayer de contourner.** Vérifier la
> version d'Ubuntu et de Python (cf. §2).

---

## 5. Campagne d'essais physiques

### Préparation — à faire AVANT chaque essai

- [ ] Zone dégagée sur **au moins 3 m** dans le sens de déplacement
- [ ] Aucun objet fragile, aucun enfant à proximité
- [ ] Télécommande officielle **en main**, bouton d'arrêt accessible
- [ ] Un adulte qui ne regarde **pas** l'écran mais **le robot**
- [ ] Batterie chargée
- [ ] Mode réel **non activé** : on commence par des scripts manuels

### Ordre obligatoire

Chaque étape est validée **avant** de passer à la suivante. En cas de doute,
arrêter et ne pas continuer.

| # | Essai | Durée | Critère de poursuite |
|---|---|---|---|
| A | Connexion seule, aucun mouvement | 1 min | le service se connecte, l'état est lu |
| B | `StandUp()` | — | le robot se lève correctement |
| C | `StandDown()` | — | il se rassoit |
| D | `StopMove()` à l'arrêt | — | arrêt **complet**, délai mesuré |
| E | `Move(0, 0, 0)` 2 s | 2 s | le robot ne bouge pas |
| F | `Move(0.2, 0, 0)` 2 s puis stop | 2 s | avance droit, s'arrête net |
| G | `Move(-0.2, 0, 0)` 2 s puis stop | 2 s | recule droit |
| H | `Move(0, 0, 0.4)` 2 s puis stop | 2 s | tourne à gauche |
| I | `Damp()` | — | immobilisation (cf. §6) |
| J | Coupure réseau pendant `Move` | 3 s | **le watchdog arrête** (cf. §11) |

### Script de connexion (essai A, sans mouvement)

```python
import sys, time
from unitree_sdk2py.core.channel import ChannelFactoryInitialize
from unitree_sdk2py.go2.sport.sport_client import SportClient

iface = sys.argv[1] if len(sys.argv) > 1 else "eth0"
ChannelFactoryInitialize(0, iface)

client = SportClient()
client.SetTimeout(10.0)
client.Init()
print("connecté")
time.sleep(2)
print("OK : connexion établie, AUCUN mouvement envoyé")
```

### Script d'essai de mouvement (essais F à H)

**Toujours** dans une `try/finally` qui appelle `StopMove()` :

```python
import sys, time
from unitree_sdk2py.core.channel import ChannelFactoryInitialize
from unitree_sdk2py.go2.sport.sport_client import SportClient

iface = sys.argv[1] if len(sys.argv) > 1 else "eth0"
ChannelFactoryInitialize(0, iface)

client = SportClient()
client.SetTimeout(10.0)
client.Init()

vx = float(sys.argv[2])
vyaw = float(sys.argv[3])
duration = float(sys.argv[4])

try:
    ret = client.Move(vx, 0.0, vyaw)
    print("code de retour de Move():", ret)   # à consigner (§7)
    # l'exemple officiel réémet en boucle : c'est une consigne persistante
    deadline = time.monotonic() + duration
    while time.monotonic() < deadline:
        client.Move(vx, 0.0, vyaw)
        time.sleep(0.005)
finally:
    client.Move(0.0, 0.0, 0.0)
    client.StopMove()
    print("StopMove() envoyé")
```

---

## 6. Qualifier le comportement d'arrêt

C'est le point le plus important de la campagne.

**Questions auxquelles il faut répondre :**

1. `StopMove()` immobilise-t-il le robot **immédiatement** ?
2. Combien de temps entre l'envoi et l'arrêt effectif ?
3. Le robot a-t-il une **inertie résiduelle** (il roule encore) ?
4. `Damp()` donne-t-il un arrêt plus sûr, ou moins ? **Il est désormais
   envoyé par la sécurité de portage, pour relâcher les pattes : il reste
   à vérifier sur le robot réel.**
5. Le robot se **relève-t-il** après un `Damp()` ? *(Il ne se relève pas tout
   seul : après un `Damp`, le service réarme quand les quatre pieds
   portent, et le programme suivant le relève.)*
6. Que se passe-t-il si on coupe le réseau **pendant** un `Move()` ?

> Si la réponse à la question 6 est « le robot continue de marcher », c'est
> **normal et attendu** : c'est précisément pourquoi le service doit être le
> propriétaire du cycle de vie avec chien de garde. Ce comportement doit être
> documenté tel quel, pas contourné.

---

## 7. Activer le mode réel

**Uniquement** si :

- [ ] tous les essais §5 sont passés ;
- [ ] le comportement d'arrêt est documenté (§6) ;
- [ ] un adulte encadrant est formé ;
- [ ] la procédure d'urgence est connue de tous (télécommande + arrêt physique).

Alors, dans `robot-service/src/go2_service/adapters/unitree.py` :

```python
physical_commands_enabled = False   # → passer à True
```

Puis, dans `main.py`, faire utiliser `UnitreeAdapter` à la place du simulateur.

> **Changer cette valeur est un acte délibéré.** Les tests
> `test_safety_adapters.py::TestUnitreeIsDisabledByDefault` échoueront, et c'est
> **voulu** : ils vous forceront à constater que vous avez changé le
> comportement par défaut.

---

## 8. Vérifier le retour de position

```python
# À faire tourner en parallèle du mouvement (essai F)
from unitree_sdk2py.core.channel import ChannelSubscriber
from unitree_sdk2py.idl.unitree_go.msg.dds_ import SportModeState_

state = {}

def on_state(msg):
    state["pos"] = msg.position()
    state["yaw"] = msg.imu_state().rpy()[2]

sub = ChannelSubscriber("rt/sportmodestate")
sub.InitChannel(on_state, 10)
```

**Question** : `position()` est-il exploitable comme retour ? Attention :

- c'est une position **estimée** par le contrôleur, pas une odométrie ;
- elle **dérive** ;
- elle peut être bruitée à l'arrêt.

Consigner la dérive observée sur 50 cm et sur 90°. La distance n'est plus un
critère d'arrêt (une translation dure la durée demandée) ; en revanche, c'est
cette mesure qui dira si la bande morte de **1°** du servo de cap est tenable
sur le robot réel.

Si l'état n'est pas exploitable, **tout déplacement se soldera par « temps
écoulé »**. C'est acceptable et honnête, mais il faut le savoir et le dire.

---

## 9. Fréquence de publication

L'exemple officiel utilise `dt = 0.005` s (200 Hz). Vérifier :

1. Que le contrôleur accepte 200 Hz sans avertissement ;
2. Ce qui se passe à une fréquence beaucoup plus basse (par exemple 20 Hz).

Si le contrôleur impose une fréquence minimale, la valeur doit être inscrite
dans `shared/safety-limits.json` (`timing.commandTickSeconds`) **et** justifiée
ici.

---

## 10. Conflits avec la télécommande et l'application officielle

- La télécommande doit rester **prioritaire**. Vérifier qu'elle arrête le
  robot même quand le service envoie des consignes.
- L'application officielle ne doit pas être lancée en même temps que le
  service.
- Si les deux se disputent le contrôle, le comportement doit être documenté et
  signalé aux animateurs.

---

## 11. Tester le chien de garde (essai J)

C'est le test le plus important du projet.

**Protocole :** robot debout, zone dégagée, adulte avec la télécommande en
main.

1. Lancer un déplacement long depuis l'interface.
2. **Couper le câble réseau** du PC qui pilote le robot (ou arrêter le
   service).
3. Observer : le robot doit s'arrêter dans le délai du bail.

**Consigner** : le délai réel entre la coupure et l'arrêt.

> Si le robot **continue** de marcher après la coupure, c'est un comportement
> attendu du SDK (consigne persistante) et **le système a échoué sur ce
> point**. Dans ce cas :
> - le mode réel **ne doit pas être activé** pour un usage avec des enfants ;
> - ou le service doit être installé sur un PC du robot (coupure réseau sans
>   effet) plutôt que sur un poste distant.

---

## 12. Résultats d'essais

**À remplir après la campagne.** Ne rien écrire avant.

| Essai | Date | Résultat | Délai d'arrêt | Conforme ? |
|---|---|---|---|---|
| A — connexion | | | | |
| B — StandUp | | | | |
| C — StandDown | | | | |
| D — StopMove à l'arrêt | | | | |
| E — Move(0,0,0) | | | | |
| F — avancer | | | | |
| G — reculer | | | | |
| H — tourner | | | | |
| I — Damp() | | | | |
| J — coupure réseau | | | | |
| §8 — dérive position | | | | |
| §9 — fréquence | | | | |
| §10 — conflit télécommande | | | | |

**Modèle exact** : ....................  **Firmware** : ....................

**Version du SDK** : ....................

**Conclusion** — cocher une seule case :

- [ ] Tous les essais sont passés. Le mode réel **peut** être activé.
- [ ] Certains essais ont échoué. Le mode réel **reste désactivé**.
      Motif : ............................................................

---

## 13. Rappel

Le bouton logiciel « Arrêter » ne remplace **jamais** :

- l'arrêt d'urgence physique du robot ;
- la télécommande officielle ;
- la surveillance attentive d'un adulte.