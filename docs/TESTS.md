# TESTS — Inventaire et résultats

## 1. Résumé

| Suite | Commande | Résultat |
|---|---|---|
| Frontend — unitaires | `cd frontend && npm test` | **217 tests, 10 fichiers, tous passants** |
| Frontend — types | `cd frontend && npm run check` | **0 erreur, 0 avertissement** |
| Frontend — build | `cd frontend && npm run build` | **réussi**, aucun avertissement |
| Service — unitaires + intégration | `cd robot-service && python -m pytest -q` | **332 tests, tous passants** |

**Total : 549 tests automatisés.**

> Un `StarletteDeprecationWarning` (concernant `httpx`) peut apparaître dans la
> sortie pytest. Il provient de la bibliothèque tierce `starlette`, pas du code
> du projet.

---

## 2. ⚠️ Ce qui a été réellement testé

### Testé sur le poste de développement

- Compilation, typage, build de production
- Logique de validation (front **et** service)
- API HTTP de bout en bout
- Communication WebSocket
- Comportement du chien de garde et du bail
- Simulateur, y compris ses pannes injectées
- Géométrie du contrôle d'obstacles : couloir, filtre du sol, cap 0/90°,
  avant/arrière/gauche/droite, seuils 1 s / 5 s
- Parcours d'interface dans un vrai navigateur

### Testé sur le robot réel (21/10/2026, autorisation adulte explicite)

Uniquement des **postures**, aucun déplacement :

| Essai | Résultat |
|---|---|
| Programme « s'asseoir » (robot debout) | `1006` puis `1007`, hauteur 0,31 m → 0,22 m ; **le chien reste assis 20 s après la fin du programme** ; aucun arrêt de sécurité |
| Programme « se relever » (robot assis) | `1002` puis `100`, hauteur 0,22 m → 0,31 m ; **aucun arrêt de sécurité** (c'est le faux « trop penché » qui est corrigé) |
| Enchaînement assis → programme suivant | le robot se relève, `safetyReason` reste `null` |
| Branchement du robot (lecture seule) | état, batterie, efforts aux pieds, code d'état lus |
| « Se coucher » (robot debout) | le corps passe de 0,32 m à 0,05 m ; **le chien reste allongé**, aucun relevé automatique (le lidar tourne librement) |
| Lidar réellement bloqué (13:55, rotation en baisse) | la rotation tombe à 0,56 de la médiane → le chien **se relève tout seul** 2,4 s après |
| Lidar réellement bloqué (14:14, rotation en hausse) | la rotation monte à 1,64 de la médiane → **non détecté** avant la correction ; le critère regarde désormais les deux sens |

### Essai de déplacement réel (22/10/2026, autorisation adulte explicite)

Après déploiement du filtre du sol par médiane, le robot `172.16.8.11` a été
connecté en WebRTC. La carte donnait avant l'essai : avant 2,845 m, arrière
1,239 m, gauche 0,571 m, droite 1,062 m. Le seuil pour 2 s était 1,10 m
(avant la réduction de la marge de trajet).

| Essai | Résultat |
|---|---|
| 2 s avant | `Move(0.30)` envoyé ; outcome `exact` ; distance lue **0,0 cm** ; **aucun mouvement** ; ni `blockedReason` ni `safetyReason` |
| 2 s arrière | `Move(-0.30)` envoyé ; outcome `exact` ; **51,4 cm** parcourus ; le robot a reculé ; aucun arrêt de sécurité |
| 1 s avant (retour) | `Move(0.30)` envoyé ; outcome `exact` ; **0,0 cm** ; aucun mouvement |
| 3 s avant, après dégagement de la caisse | `Move(0.30)` envoyé ; outcome `exact` ; **0,0 cm** ; aucun mouvement ; la position/odométrie a ensuite sauté de plusieurs dizaines de centimètres sans commande, signe d'une relocalisation |
| 1 s arrière (retour) | `Move(-0.30)` envoyé ; outcome `exact` ; **0,0 cm** ; aucun mouvement ; aucun arrêt de sécurité |
| Position finale | **non vérifiée** ; la pose SLAM a dérivé/relocalisé plusieurs fois ; la distance de retour n'est pas vérifiable par la carte |

L'avance n'a pas été obtenue alors que la commande est partie et que la carte
la déclarait libre (2,242 m à l'avant après dégagement, seuil 1,40 m pour 3 s
avant la réduction de la marge de trajet).
Cause probable : protection/anti-obstacle interne du robot, la caisse grise
restant à environ 0,64 m sur le côté gauche. **Le contrôle d'obstacles du
service n'est donc pas validé physiquement.**

### Essai après réduction de la marge de trajet (22/10/2026)

La marge de trajet a été ramenée de 0,10 à 0,05 m. La carte donnait 2,056 m
libres devant et aucune case derrière ; le robot a été reconnecté, puis un pas
de 3 s a été envoyé :

| Essai | Résultat |
|---|---|
| 3 s avant | `Move(0.30)` ; outcome `exact` ; distance odométrique annoncée **0,0 cm** (publication en retard) ; déplacement lu après stabilisation **environ 37,5 cm** ; le robot s'arrête ensuite, sans `safetyReason` |
| 1 s arrière (retour) | `Move(-0.30)` ; outcome `exact` ; déplacement lu **environ 1,6 cm** ; quasi immobile |
| 2 s arrière (retour) | `Move(-0.30)` ; outcome `exact` ; distance odométrique annoncée **0,0 cm** ; déplacement de pose lu après stabilisation **environ 2,8 cm** ; quasi immobile |
| Position finale | **non revenue au départ** ; les reculs n'ont pas compensé l'avance ; la position exacte n'est pas fiable à cause des relocalisations |

Le robot avance donc un peu (environ 37 cm), puis s'arrête dans le passage
étroit entre le meuble gris et la poutre ; le recul ne le dégage pas. La marge
du service n'est pas le facteur limitant : c'est l'anti-obstacle interne du
robot. **Le contrôle d'obstacles du service n'est toujours pas validé
physiquement.**

### ❌ NON testé ou non validé

> **Des essais de mouvement réels ont été effectués le 22/10/2026** (2 s avant,
> 2 s arrière, 1 s avant, puis 3 s avant et 1 s arrière après dégagement de la
> caisse, enfin 3 s avant et retours après réduction de la marge). Un recul de
> 2 s a déplacé le robot de 51,4 cm ; l'avance de 3 s après réduction l'a
> déplacé d'environ 37,5 cm, puis il s'est arrêté ; les reculs de 1 s et 2 s
> n'ont pas compensé. L'essai reste **incomplet**.

- Connexion WebRTC réelle établie ; état, lidar et caméra lus ; des essais de
  mouvement ont été envoyés.
- Déplacement physique réel : un recul de 51,4 cm ; une avance d'environ
  37,5 cm après réduction de la marge, mais pas les 0,9 m attendus pour 3 s ;
  les retours de 1 s et 2 s n'ont déplacé le robot que de quelques centimètres.
  **Aucun retour au départ n'a été obtenu.**
- Aucun test d'arrêt d'urgence ni de coupure réseau sur un robot réel.
- Mesures de distance non fiables : l'odométrie est publiée en retard (0,0 cm
  annoncé pour une avance de 37,5 cm) et la pose SLAM se relocalise. Les sauts
  de pose observés sans commande ne sont pas des distances fiables.
- **Aucun test réel de portage** : la décision, l'envoi de `Damp` et le
  verrouillage sont testés sur des topics simulés, pas en soulevant le
  robot. Le `Damp` de sécurité n'a donc **jamais** été envoyé au robot.
- **Contrôle d'obstacles non validé sur le robot réel** : le robot
  `172.16.8.11` a été joint et la carte réelle lue. Après réduction de la marge,
  l'avance a bien eu lieu, mais seulement sur environ 37,5 cm, puis le robot
  s'est arrêté **sans** `safetyReason` du service. La cause probable est
  l'anti-obstacle interne du robot dans le passage étroit (meuble gris/poutre),
  pas le contrôle du service. La géométrie et le filtre médian sont testés avec
  des cartes synthétiques ; les distances réelles et le retour restent **à
  vérifier** (voir `docs/ROBOT_SETUP.md`).
- L'assiette n'est plus un critère d'arrêt : le seuil de 45° a été retiré
  après un faux arrêt pendant « s'asseoir » puis « se relever ».
- **Interrupteur « Sécurité » non actionné sur le robot réel** : le
  `22/10/2026`, après redéploiement, le robot `172.16.8.11` était injoignable
  (`Destination Host Unreachable`), donc la reconnexion WebRTC a échoué. Le
  service est resté en simulation et l'endpoint a répondu `409` comme prévu.
  La coupure/réactivation réelle reste à vérifier dès que le robot est
  rallumé.

Les préflight des gestes `Hello` et `Stretch` ont été refusés sans autorisation
adulte (HTTP 403), donc aucune commande n'est partie.

L'adaptateur `UnitreeAdapter` (DDS) est **écrit** d'après l'API officielle lue
dans le dépôt Unitree, mais il est **désactivé** (`physical_commands_enabled =
False`) et n'a jamais été exécuté. Le chemin réel utilisé est `WebRTCAdapter`,
qui a été connecté au robot et a exécuté l'essai de mouvement ci-dessus.

Le mode réel est refusé **par défaut** tant que l'adaptateur n'a pas établi une
connexion physique (`physical_commands_enabled` reste `False`). Après la
connexion WebRTC réelle du 22/10/2026, l'adaptateur a activé les commandes.
Le test `test_even_with_an_adult_real_mode_is_not_available` vérifie le refus
par défaut, pas le refus après connexion.

---

## 3. Tests frontend (217)

### `tests/commands.test.ts` — modèle de commandes
- Acceptation de chaque genre de commande
- Refus des genres inconnus, paramètres manquants
- Refus de `NaN`, `Infinity`, chaînes, booléens
- Refus des structures non-objet
- Classification des capacités
- Cumuls de distance et d'angle

### `tests/validate.test.ts` — validation
- Programme vide, programme cohérent
- Bornes exactes acceptées, juste hors limites refusées
- Valeurs négatives traitées en valeur absolue
- Durées d'attente hors plage
- Dépassement du nombre d'étapes, de la distance totale, de la durée
- Capacité indisponible selon l'adaptateur
- **Commande forgée** (`self_destruct`) rejetée

### `tests/motion.test.ts` — modèle de mouvement
- Conversion distance → durée à la vitesse configurée
- Conversion angle → durée
- Valeur absolue, durée minimale (protection division par zéro)
- Cohérence distance/durée
- Signes des consignes avant/arrière et gauche/droite
- Rotation pure sans vitesse linéaire
- Vitesses jamais supérieures aux limites
- Marge de sécurité du délai

### `tests/compiler.test.ts` (19) — traduction blocs → instructions
Espace de travail Blockly *headless*, sans rendu DOM.

- **Chaque bloc paramétré expose un champ nommé** (`DISTANCE`, `ANGLE`,
  `DURATION`, `COUNT`) — régression du bug « champs non enregistrés »
- Valeurs par défaut conformes aux bornes (50 / 90 / 2 / 3)
- La valeur saisie est lue par le compilateur (137 cm)
- Les blocs sans paramètre n'ont pas de champ de valeur
- Chaîne simple traduite dans l'ordre, sans message d'erreur
- **Répétitions** : 3 par défaut, 5 saisies, **imbrication** (2 × 3 = 6)
- Répétition non entière et répétition nulle refusées
- Champ borné : une répétition nulle revient à 1
- Cycle de blocs : la compilation se termine, sans boucle infinie
- Programme sans bloc de départ, et bloc non rattaché : signalés

### `tests/settings.test.ts` (14) — réglages
- Descripteurs : 10 réglages, tous avec libellé, aide et pas ; aucun doublon
- Préférences : défaut, enregistrement/relecture, URL non-http **refusée**
  (`file://`, `javascript:`), URL invalide ignorée à la lecture, thème inconnu ignoré
- Préférences : survie à un stockage corrompu
- Effet sur la validation : la vitesse abaissée allonge bien la durée estimée
- Effet sur la validation : un programme de 60 pas est accepté (défaut) mais
  refusé si le service règle `max_total_steps` à 50
- Effet sur la validation : une distance refusée sous la limite abaissée
- Valeurs de réglage aberrantes (`NaN`, `Infinity`) ignorées sans planter
- Les champs non transmis gardent la valeur du fichier partagé

### `tests/storage.test.ts` — missions
- Enregistrement et relecture
- Mise à jour sans doublon
- Nom vide / trop long refusé
- XML non-Blockly refusé
- Suppression ciblée
- **Données non fiables** : nom vide, XML invalide, version de schéma
  inconnue, XML surdimensionné, stockage corrompu, entrée partiellement
  corrompue

### `tests/app-store.test.ts` — action bloquée
- Une étape `blocked` garde son message (« Pas assez de place devant… ») et
  n'est **pas** affichée comme terminée
- Le bilan final est un avertissement (« je n'ai pas fait les actions… »)
- Sans message du service, l'étape est nommée « pas assez de place »
- **Fenêtre centrale** : le message complet est conservé, le titre dépend de la
  direction, et `Fermer` efface la fenêtre
- Un obstacle qui apparaît **pendant** le pas (`stopped` avec message
  « obstacle ») ouvre aussi la fenêtre
- **Interrupteur de sécurité** : appel API avec `adult_authorised`, état
  `obstacleSafetyEnabled` mis à jour, avertissement à la coupure, retour à
  l'état actif à la réactivation

---

## 4. Tests du service (332)

### `test_obstacles.py` (31) — géométrie pure du contrôle d'obstacles
- Le sol et le plafond sont retirés (hauteur mesurée depuis la médiane des
  hauteurs) ; un objet de moins de 25 cm est ignoré
- Un voxel aberrant sous le sol ou un sol épais ne transforme pas le plancher
  en mur ; l'ancien minimum absolu et le 10e percentile auraient échoué
- Une carte vide ne prouve pas un mur ; une résolution nulle est refusée
- Distance libre devant, derrière, à gauche, à droite, cap 0° et 90°
- Le couloir de ± 0,30 m : un mur juste dedans compte, juste dehors non
- Pas latéral : couloir élargi à ± 0,45 m (le corps est en travers) et
  distance nécessaire de 0,60 m pour 0,30 m parcourus
- La case la plus proche gagne ; on retire une case entière (5 cm)
- La position du robot est soustraite ; une case derrière est ignorée
- Seuils : 1 s à 0,30 m/s exige 0,75 m, 5 s exige 1,95 m — un mur à 1 m
  laisse passer 1 s mais pas 5 s
- Messages en français, avec la virgule décimale

### `test_validation.py` (35) — configuration et validation autoritative
- Le fichier partagé est bien lu, et les **cohérences** vérifiées :
  battement < bail < durée maximale du programme
- Bornes de mouvement positives et ordonnées
- Analyse de chaque genre de commande, refus des données forgées
- Validation des plages, des cumuls, de la durée, des capacités
- Chaque erreur porte son **index** pour la localisation
- Intégrité du fichier JSON partagé

### `test_execution.py` — moteur, adaptateur simulé, sécurité
- Planification : durées, signes, absence de vitesse linéaire sur une rotation
- **Garde de vitesse** : refus d'une vitesse excessive, acceptation à la limite
- Écart angulaire par le plus court chemin (179° → -179° = 2°)
- Simulateur : connexion, déconnexion, refus hors connexion
- Mesure réellement différente de la consigne (dérive simulée)
- Robot bloqué → « temps écoulé », **jamais** « réussi »
- Signal d'arrêt interruptible à tout moment
- Perte de connexion en cours de mouvement
- Posture : aucune mesure inventée
- Moteur : ordre d'exécution, interruption, refus de concurrence
- **Contrôle d'obstacles** : pas assez de place → l'action est sautée, le
  programme continue, l'étape n'est pas annoncée « terminée » ; assez de
  place → l'action part ; mesure absente (simulateur) → l'action part ;
  direction correcte pour avant/arrière/gauche/droite ; rotation non contrôlée
- Récupération après erreur (pas de verrouillage)
- `request_stop()` appelé à la fin, même sur exception
- Chien de garde : pas de déclenchement sans exécution, pas avec battements,
  **déclenchement à l'expiration du bail**
- **Arrêt de sécurité** : `SafetyInterrupt` termine le programme en `safety`,
  sans instruction suivante ; la préparation est aussi couverte
- **Verrouillage** : le chien de garde lit `safety_stop_reason` et demande
  l'arrêt en `safety`
- **Branchement** : `adopt_robot_adapter` arrête l'ancien chien de garde puis
  en démarre un nouveau ; `release_robot_adapter` fait de même en simulation
- Arrêt d'urgence, mesure de l'âge du bail
- `StopSignal` : première raison conservée, réinitialisation

### `test_state_safety.py` (11) — décisions pures de portage
- Quatre pieds chargés → aucun arrêt ; somme < 60 → arrêt
- Seuil exact : 60 accepté, 56 refusé
- Un seul pied vide ne suffit pas ; mesure absente, incomplète ou périmée
  → aucune conclusion
- `Sit`/`Damp` volontaire exclu, même avec pieds à zéro
- Réarmement : quatre appuis pendant 1 s ; une mesure absente ne réarme pas
- Réarmement possible **allongé** après `Damp`, dès que les pieds portent
- Un nouveau portage après réarmement redéclenche

### `test_webrtc_safety.py` (20) — intégration aux topics réels
- `foot_force` lu dans `rt/lf/lowstate`
- Portage debout → `Move(0,0,0)` + `StopMove` + `Damp`, verrouillage visible
  dans `get_status().safety_reason` et `state=error`
- La fin du programme (`request_stop`) ne lève pas ce verrouillage et ne
  renvoie pas `Move` après `Damp`
- Robot assis ou mesure absente → aucun arrêt
- Mesure réelle au repos `[86, 97, 86, 89]` → aucun arrêt
- Deux échantillons d'IMU à 50° → **aucun arrêt** (régression du faux arrêt
  « trop penché »)
- Fenêtre de grâce après une posture volontaire, y compris le relèvement,
  puis détection après la fenêtre
- Préparation et commande de mouvement refusées par `SafetyInterrupt` ;
  `STOP` accepté sans renvoyer de commande
- Distance libre lue depuis la pose du robot et les cases d'obstacles ;
  sans pose, carte périmée ou pose périmée → `None` (pas de décision)
- **Sécurité lidar désactivée** → `clearance_m()` renvoie `None`, donc aucune
  décision de blocage du service
- Une action bloquée avant le premier pas renvoie `blocked` et n'envoie
  **aucun** `Move`
- Le maillage 3D retire le sol, le plafond et l'objet bas : seul le mur reste

### `test_posture.py` (21) — postures : rester assis, repartir sur quatre pattes
- Un robot **assis** ne reçoit ni `Move` ni `StopMove` à l'arrêt : les deux
  le relèvent
- Un robot qui **publie 1007** (assis) ne reçoit rien non plus, même si le
  dernier ordre envoyé était « debout »
- Un robot debout reçoit la consigne nulle et `StopMove`
- Le code d'état prime sur la hauteur ; sans mesure ni ordre, on ne suppose
  pas qu'il soit debout
- Un bond (0,52 m d'odométrie) ne pollue pas la hauteur de référence
- Le robot n'est prêt à bouger qu'en `100` ; en transition (`1002`) aucune
  consigne de mouvement ne part
- Un programme commence toujours par un `StandUp` si le robot n'est pas
  debout
- Une posture refusée est réessayée une fois, puis signalée
- **Acquittement perdu** : la posture **publiée** par le robot (`1007`) fait
  foi — l'instruction est alors acquittée, sans réponse du robot
- Sans acquittement **ni** posture publiée, le résultat est un échec, jamais
  un « réussi » inventé
- « Se coucher » : vérifié sur l'état publié (`1001`) et **renvoyé** si le
  robot n'a pas obéi
- Un robot en train de se poser (`1006`) ne reçoit **aucune** consigne de
  vitesse à l'arrêt : `Move` le relèverait

### `test_recovery.py` (21) — relevé automatique
- Allongé + lidar bloqué + « se coucher » demandé → le robot se relève
- La confirmation est obligatoire (0,6 s)
- Lidar libre → **rien** : c'est le cas le plus fréquent
- Lidar inconnu, ou pas assez de mesures → aucune conclusion
- Robot **tombé** (nous ne l'avons pas allongé) → pas de relevé
- Programme en cours → pas de relevé
- Robot debout → pas de relevé
- Une situation interrompue repart de zéro
- Mesure : `dirty_percentage` à 63 % **ne** signifie pas « bloqué » ; c'est
  la rotation réelle qui compte
- **Un pic de mesure ne bouge pas l'échelle** (régression : le maximum
  faisait passer l'échelle de 3,6× et tout paraissait bloqué)
- Un relèvement (−10 % de la médiane) n'est pas un blocage
- Lidar bloqué **en dessous** (−44 %) → bloqué
- Lidar bloqué **au-dessus** (+64 %) → bloqué (l'autre forme du blocage)
- Un blocage durable ne déplace pas la référence
- Le `Damp` du bloc « se coucher » arme le relevé
- Le relevé part quand le lidar est bloqué, et **seulement** alors

### `test_motion_safety.py` — conditions d'arrêt
- **Dépassement** : le robot s'arrête au lieu de continuer
- Seuil bas et non `abs(diff) <= tolérance`
- Robot bloqué → délai dépassé, jamais « réussi »
- Le délai de sécurité borne effectivement la durée
- Le bloc « S'arrêter » est une instruction, pas une annulation

### `test_safety_adapters.py` — garde-fous de l'adaptateur
- L'adaptateur physique est **désactivé par défaut**
- `connect()` et `execute_command()` refusés quand il est désactivé
- Les éléments non vérifiés restent déclarés
- Le sujet DDS correspond à l'exemple officiel (`rt/sportmodestate`)
- Les deux adaptateurs respectent le même contrat
- Le simulateur ne mentionne **pas** le SDK
- **Aucune commande basse niveau** (`lowcmd`, `crc32`, `motor_cmd`…) dans le
  code — vérifié sur l'AST, pas sur le texte, pour ne pas confondre une
  mention en commentaire avec une implémentation
- Capacités limitées aux quatre du projet
- `get_status()` ne lève jamais

### `test_settings.py` (36) — réglages d'adulte
- **Isolation** : `create_app` reçoit sa propre copie ; deux apps ne se
  contaminent pas ; le cache de `load_limits` n'est jamais altéré
- Le fichier partagé reste au niveau des plafonds (le code et les données ne divergent pas)
- `load_limits` mis en cache : un test ne peut pas modifier les réglages d'un autre
- Application d'une valeur valide, champs omis laissés intacts
- **Valeur au-dessus du plafond refusée, sans écriture partielle**
- Valeur sous le plancher, champ inconnu, booléen, chaîne, `NaN`/`Infinity` : refusés
- Bornes exactes acceptées, payload vide sans effet
- Cohérence : distance totale ≥ un pas, cumul atteignable en un nombre de pas donné
- Cohérence : une attente ne peut pas dépasser la durée du programme
- Chaque réglage modifiable a bien un plancher et un plafond
- API : `GET` renvoie valeurs + bornes, bornes ≤ plafonds du code
- API : refus sans autorisation adulte, refus pendant une exécution (409)
- API : changement accepté → `settingsRevision` incrémenté ; refusé → inchangé
- API : `adultAuthorised` (camelCase) **refusé** sur les trois routes
- API : `adult_authorised` accepté sur les trois routes

### `test_api.py` — intégration HTTP
- Démarrage en simulation, état et capacités ; `obstacleSafetyEnabled` vaut
  `true` et `obstacleSafetyAvailable` est `false` sans robot réel
- Mode réel refusé sans autorisation adulte
- **Mode réel refusé par défaut**, même AVEC autorisation, tant qu'aucun
  adaptateur physique n'est connecté
- **Interrupteur de sécurité** : refus en simulation (409), refus d'un champ
  camelCase (422), coupure autorisée seulement avec `adult_authorised`,
  réactivation sans autorisation, état de l'adaptateur mis à jour
- Validation de la forme : genre inconnu, paramètre manquant, programme non
  liste, booléen, `NaN`
- Programmes dépassant les limites
- Démarrage asynchrone (la requête ne bloque pas)
- Refus d'une exécution concurrente (409)
- Arrêt et battement
- Injection de pannes : perte de connexion, commande refusée, robot bloqué
- Origine WebSocket refusée / acceptée
- Arrêt demandé à la fermeture du service
- **Contrat de battement** : `run_id` accepté, `runId` **rejeté** (non-régression)
- Battements empêchant l'expiration du bail, et **contrôle inverse** : sans
  battement, le chien de garde agit

---

## 5. Parcours vérifié dans un vrai navigateur

Realisé sur le poste de développement, service et interface en fonctionnement :

| Étape | Résultat |
|---|---|
| Chargement de l'interface | aucune erreur console |
| Affichage de la palette en français | 4 catégories : Quand ça commence, Déplacements, Actions, Contrôle |
| Ouverture d'une catégorie | 5 blocs de déplacement listés |
| Bloc de départ | « Quand je clique sur Démarrer » affiché correctement |
| Ajout d'un bloc par glisser-déposer | bloc créé sur l'espace de travail |
| Bloc non rattaché | ⛔ « Un bloc est seul, pas attaché au programme. » |
| Bouton Démarrer désactivé | oui, quand le programme est invalide |
| Programme valide | ✅ « Bravo ! Ton programme est prêt. » |
| Étapes listées | 4 étapes en français, dans l'ordre |
| Exécution complète | ✅ « Terminé ! Le programme s'est bien déroulé. » |
| Mesures affichées | « Avancer de 50 cm → mesuré · 45 cm », « Tourner à gauche de 90° → mesuré · 82.1° » |
| Posture | « terminé » (et **non** « mesuré », faute de mesure SDK) |
| Arrêt en cours d'exécution | ⚠️ « Le programme a été arrêté. » |
| Connexion au service | badge « Robot connecté » |
| Interrupteur « Sécurité » (simulation) | visible en haut à droite, désactivé, mention « indisponible » |
| Fenêtre d'obstacle, message long | texte complet affiché au centre, sans coupure ; bouton **Fermer** fonctionnel |
| Fenêtre d'arrêt pendant le pas | titre « Un obstacle est trop proche », sous-titre « Le robot s'est arrêté à temps » |
| Sécurité coupée (état injecté) | interrupteur rouge « désactivée », aucun bandeau supplémentaire sous l'en-tête |
| Clic pour couper (état injecté) | fenêtre « Désactiver la sécurité ? » ; **Annuler** laisse la sécurité active |

> Vérification du `22/10/2026` sur l'interface de développement, avec un message
> d'obstacle et un état « robot réel, sécurité coupée » injectés dans l'état de
> l'application (le robot n'était pas joignable pour provoquer un vrai
> blocage). Le rendu 3D n'a pas pu être contrôlé dans le navigateur de test, qui
> n'avait pas de contexte WebGL ; cela ne concerne ni la fenêtre ni
> l'interrupteur.

### Bugs trouvés et corrigés grâce à ce parcours

**1. Les battements de sécurité étaient tous refusés.**
Le frontend envoyait `{"runId": …}` alors que le service attendait
`{"run_id": …}`. Le bail expirait et **le chien de garde arrêtait le robot au
bout de 1,5 s**. C'est exactement le comportement voulu du système de
sécurité, mais c'était un vrai défaut. Corrigé, verrouillé par
`TestHeartbeatContract`.

**2. Le même piège, sur l'autorisation adulte.**
Le frontend envoyait `adultAuthorised` au lieu de `adult_authorised`. Pydantic
ignorait silencieusement le champ, la valeur restait `False`, et le service
répondait « Seul un adulte peut modifier les réglages » — message trompeur
alors que l'adulte avait cliqué sur *Appliquer*. Corrigé, et **tous** les
modèles de requête passent maintenant par `extra="forbid"` pour qu'une erreur de
forme de payload soit visible immédiatement. Verrouillé par
`TestSettingsApi::test_post_rejects_camel_case_authorisation` et ses variantes
sur `/api/execution/start` et `/api/mode`.

**3. La zone de blocs n'utilisait pas toute la surface.**
`Blockly` figeait ses dimensions à l'injection et ne suivait pas le
redimensionnement du conteneur. Corrigé par un `ResizeObserver` appelant
`resize()` puis `svgResize()`, plus deux `requestAnimationFrame` pour les
premières frames. Vérifié : la zone SVG suit exactement son conteneur au
chargement **et** après redimensionnement.

**4. Deux tests étaient instables selon l'ordre d'exécution.**

`load_limits()` est mis en cache et renvoie le même objet ; `apply_settings()`
le modifie en place. Une application créée dans un test altérait donc le service
des autres. Corrigé par une copie dans `create_app()`, et verrouillé par
`TestLimitsIsolation` (deux apps indépendantes, cache non altéré).

Un second test, lui, était une course contre la scrutation du chien de garde :
le délai fixe pouvait tomber juste avant le tour suivant. Il attend désormais
la survenue effective du déclenchement. Vérifié sur **8 exécutions
consécutives sans échec**.

### Bugs de blocs — trouvés et corrigés

**5. Les champs numériques n'existaient pas.**
Signalé : « je ne vois pas les blocs pour choisir les durées ». Dans la
palette, les blocs affichaient « Avancer de ␣ cm » avec une entrée vide.

Cause : le parseur JSON de Blockly 13 **n'instancie pas** une clé `shadow`.
Ni `appendShadowInput()` ni `setShadowInput()` n'existent dans cette version.
La déclaration JSON était donc silencieusement ignorée.

**6. Les champs n'étaient pas enregistrés.**
En déclarant les blocs en JavaScript, `input.appendField(field)` sans nom
laisse `field.name === undefined` : le champ est affiché mais **pas enregistré**
dans le bloc. `getFieldValue('DISTANCE')` renvoyait `null` et le compilateur
concluait « il manque un nombre ».

Les blocs portent maintenant un champ nommé, éditable directement.

**7. L'état validé était périmé.**
Vérifier et Démarrer travaillaient sur le dernier état connu de l'éditeur.
Un changement déposé juste avant le clic n'était pas pris en compte : le robot
allait exécuter autre chose que ce qui était annoncé. L'éditeur expose
désormais `refresh()`, appelé au moment même de Vérifier et Démarrer — sans
dépendance aux événements de changement de Blockly, qui ne se déclenchent pas
de façon fiable ici.

### Réglages — vérifié en exécution

| Étape | Résultat |
|---|---|
| Ouverture du panneau | 10 curseurs affichés, valeurs du service |
| Bornes affichées sous chaque curseur | plancher → plafond, corrects |
| Modification d'un curseur | cadre bleuté, saisie de confirmation demandée |
| Bouton Appliquer désactivé | tant que le mot n'est pas saisi |
| Application | ✅ « Réglages appliqués. », service à 0,15 m/s |
| Vérification du service | `GET /api/settings` renvoie bien 0,15 |
| Tentative de dépasser le plafond (99 m/s) | **422 refusé**, valeur inchangée |
| Réglage refusé en pleine exécution | **409** |
| Programmes déjà vérifiés | invalidés (nouvelle révision) |

### Blocs — vérifié en exécution

| Étape | Résultat |
|---|---|
| Palette « Déplacements » | 4 blocs chiffrés : 50 cm, 50 cm, 90°, 90° |
| Palette « Quand ça commence » | « Quand je clique sur Démarrer » + « 2 secondes » |
| Palette « Contrôle » | « 3 fois » |
| Blocs sans paramètre | aucun champ (normal) |
| Programme « debout, 120 cm, 45°, 3 s » | 4 étapes correctes |
| Bloc lâché hors programme | ⛔ « Un bloc est seul, pas attaché au programme. » |
| Modification d'un nombre puis Vérifier | « Avancer de 150 cm » pris en compte |
| Ajout d'un bloc libre puis Vérifier | détecté immédiatement |

---

## 6. Tests physiques — protocole

**Aucun test de mouvement automatisé ne doit être lancé.**

La procédure complète est dans `docs/ROBOT_SETUP.md` §5. En résumé :

1. Vérifications **sans mouvement** (connexion).
2. Postures.
3. Arrêt à l'arrêt.
4. Déplacements courts, **un à la fois**, à 0,2 m/s.
5. Coupure réseau pendant un mouvement (essai le plus important).

Préconditions à chaque essai : zone dégagée sur 3 m, télécommande en main,
adulte watching le robot, pas d'enfant à proximité.

---

## 7. Lancer tous les tests

```bash
# Frontend
cd frontend
npm test
npm run check
npm run build

# Service
cd robot-service
python -m pytest -q
```

### Avant de livrer

- [ ] 46 + 131 tests passants
- [ ] 0 erreur de type
- [ ] build sans avertissement
- [ ] aucun message « fonctionnalité n'est pas disponible » présenté comme opérationnel
- [ ] `README.md` à jour sur l'état d'avancement
- [ ] `docs/ROBOT_SETUP.md` **non rempli** ⇒ mode réel désactivé