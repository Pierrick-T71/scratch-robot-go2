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
| `Damp()` | C++ et Python | ✅ arrêt de sécurité (à qualifier) |
| `BalanceStand()`, `RecoveryStand()` | C++ et Python | ✅ mais inutilisés ici |
| `HandStand`, `LeftFlip`, `BackFlip`, `FreeWalk`, `FreeBound`, `FreeAvoid`, `WalkUpright`, `CrossStep`, `FreeJump` | Python | ❌ **écartés** : acrobaties dangereuses |
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
| 8 | `Damp()` est-il l'arrêt le plus sûr ? | essai §6 |
| 9 | Signification du code d'erreur retourné par `Move()` | essai §7 |
| 10 | Fiabilité de `position()` comme retour | comparaison §8 |
| 11 | Fréquence de publication acceptée | essai §9 |
| 12 | Interface réseau : `ip addr` montre `eth0` ? | `ip -br addr` |
| 13 | La télécommande officielle et l'app Unitree ne rentrent-elles pas en conflit ? | essai §10 |
| 14 | Les licences/options autorisent-elles le contrôle programmatique ? | documentation Unitree |

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
4. `Damp()` donne-t-il un arrêt plus sûr, ou moins ?
5. Le robot se **relève-t-il** après un `Damp()` ?
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

Consigner la dérive observée sur 50 cm et sur 90°. C'est cette mesure qui
déterminera si les tolérances (5 cm / 8°) sont réalistes.

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