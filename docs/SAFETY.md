# SAFETY — Sécurité du robot et des enfants

Ce document est le référentiel sécurité du projet. Il s'adresse d'abord aux
adultes encadrants.

> **Résumé en une phrase :** le logiciel ne peut pas remplacer la
> surveillance d'un adulte et l'arrêt d'urgence physique du robot.

---

## 1. Le risque principal

Un Go2 pèse environ 12 kg et se déplace à 0,3 m/s. Il peut :
- heurter une personne (notamment un enfant) au niveau des jambes ;
- tomber et injure quelqu'un ;
- pincer un pied entre ses pattes.

### Pourquoi le logiciel seul ne suffit pas

Lu dans l'exemple officiel du SDK (`go2_sport_client.cpp`) :

```cpp
sport_client.Move(0.3, 0, 0.3);
```

`Move()` pose une **consigne de vitesse persistante**. L'exemple officiel ne
fait **jamais** de `StopMove()` en sortie de boucle.

> **Conséquence directe :** si le service s'arrête, se fige ou perd le réseau,
> le robot **peut continuer de marcher** avec sa dernière vitesse.

Aucun bouton logiciel ne peut empêcher cela. D'où les trois niveaux de
protection mis en place.

---

## 2. Trois niveaux d'arrêt

| Niveau | Moyen | Qui agit | Délai |
|---|---|---|---|
| 1 | Bouton « Arrêter » de l'interface | l'enfant | ~1 s |
| 2 | Chien de garde du service | automatique | ≤ 1,5 s |
| 3 | **Télécommande / arrêt physique** | l'adulte | immédiat |

Le niveau 3 est le seul garanti. Les niveaux 1 et 2 sont des aides, pas des
garanties.

---

## 3. Protections avant l'exécution

| Protection | Implémentation |
|---|---|
| Simulation par défaut | `ServiceState._mode = "simulation"` au démarrage, non modifiable par le frontend seul |
| Autorisation adulte | case à cocher + saisie du mot `ROBOT` dans `ModeSwitch.svelte` |
| Confirmation de zone dégagée | case obligatoire dans la même fenêtre |
| Confirmation avant chaque démarrage réel | fenêtre « Le robot va vraiment bouger » |
| Robot connecté et sain | refus du service si `state` vaut `error` ou `disconnected` |
| Validation du programme | refus avec message et emplacement de l'erreur |
| Pas d'exécutions concurrentes | HTTP 409 si une exécution est en cours |

---

## 4. Protections pendant l'exécution

| Protection | Mécanisme |
|---|---|
| **Bail de sécurité** | le frontend bat toutes les 500 ms ; sans battement pendant 1,5 s, arrêt |
| **Chien de garde** | boucle indépendante, surveille au tiers du délai |
| Vitesse bornée | `maxLinearSpeed` 0,3 m/s, `maxAngularSpeed` 0,5 rad/s |
| Double garde de vitesse | validation du programme **et** `assert_speed_within_limits()` avant publication |
| Durée bornée | `maxProgramSeconds` 120 s |
| Distance bornée | `maxTotalDistanceCm` 1500 cm, 200 cm par pas |
| Rotations bornées | `maxTotalAngleDeg` 3600°, 180° par pas |
| Étapes bornées | `maxTotalSteps` 500 |
| Délai par déplacement | `durée_nominale × 2,5 + 1 s`, puis arrêt |
| Fin garantie | `request_stop()` appelé dans un `finally` — même sur exception |
| État toujours affiché | progression et état du robot visibles en permanence |
| **Portage / pieds dans le vide** | `foot_force` (état bas) : somme sous 60 → `Move(0)`, `StopMove`, `Damp` au prochain message (≈ 0,5 s) et verrouillage |
| **Relevage automatique** | robot allongé **par nous** + lidar bloqué (rotation réelle en chute) → il se relève tout seul |

### Détection de portage

Le 21 octobre 2026, une protection a été ajoutée dans l'adaptateur WebRTC.
Elle répond à un risque concret : un robot soulevé pendant une marche continue
de battre des pattes pour retrouver son équilibre, puis repart dès qu'il
retrouve un appui.

**Mesure utilisée**

| Mesure | Topic | Règle |
|---|---|---|
| Efforts sous les quatre pieds | `rt/lf/lowstate` → `foot_force` | somme **< 60** = aucun appui |

Le seuil de 60 vient des mesures existantes : `docs/ROBOT_SETUP.md` indique
qu'un `foot_force` nul signifie que le pied ne touche plus le sol, et
`.setup/test_sauts3.py` utilise déjà `somme < 60` pour « les pieds ne portent
plus ». Au repos, la **somme** relevée est de l'ordre de 300 : 274 pendant les
essais de saut, et **358 à 360** à la connexion du 21/10/2026
(`[86, 97, 86, 89]`, puis `[86, 101, 85, 88]`). Le seuil de 60 reste donc très
en dessous d'un appui normal.

**Pourquoi l'assiette n'est plus surveillée**

La première version arrêtait aussi le robot au-delà de 45° de roulis ou de
tangage. Ce seuil a produit un **faux arrêt** pendant un enchaînement normal
« s'asseoir puis se relever » : l'IMU voit la transition, pas seulement la
posture finale. Le 21 octobre 2026, ce critère a été retiré. Seule la décharge
des quatre pieds déclenche désormais l'arrêt.

Conséquence assumée : un robot penché ou sur une pente, mais avec les pieds
chargés, n'est **pas** arrêté automatiquement. L'adulte doit intervenir.

**Ce qui se passe**

1. L'adaptateur annule la consigne de vitesse (`Move(0, 0, 0)`).
2. Il envoie `StopMove`.
3. Il envoie `Damp` : c'est le seul ordre du SDK qui coupe l'équilibrage
   actif. Les pattes cessent de chercher un appui et se relâchent. Le robot
   devient mou : la personne qui le porte doit le tenir fermement.
4. Un verrouillage bloque toute nouvelle commande.
5. Le programme en cours se termine avec la raison `safety` ; le chien de
   garde le constate aussi.
6. L'interface affiche un bandeau rouge avec la raison et la consigne
   « repose-le au sol ».

### Le robot s'est allongé et son lidar frotte le sol

Le lidar du Go2 est monté **devant la tête**. Quand le chien est allongé, sa
fenêtre tournante peut frotter le sol : le moteur force, le chien s'use, et
la carte du lidar devient illisible.

Dans ce cas précis — et **seulement** dans ce cas — le robot se relève tout
seul.

| Condition | Effet |
|---|---|
| Le robot est allongé (`1001`) | — |
| **C'est nous qui l'avons allongé** (bloc « se coucher ») | — |
| **Le lidar est bloqué** | → le robot se relève (`StandUp`) |
| Un programme est en cours | c'est le programme qui prépare le robot, pas le relevé automatique |
| Le lidar tourne librement | le chien reste allongé, comme demandé |

**Comment on sait que le lidar est bloqué ?**

Le lidar publie (`rt/utlidar/lidar_state`) sa rotation **réelle**
(`com_rotation_speed`) et la rotation **demandée** (`sys_rotation_speed`).
Quand sa fenêtre frotte contre le sol, le moteur force : la rotation réelle
chute.

Le service compare la rotation réelle à la **médiane** des rotations
récentes (60 mesures), et considère le lidar bloqué quand elle s'écarte de
plus de **25 %** de cette médiane — **dans les deux sens**. Une erreur
firmware (`error_state` non nul) compte aussi comme un blocage.

Mesures réelles du 21/10/2026 (ratio = rotation réelle / rotation demandée) :

| Situation | ratio | écart à la médiane |
|---|---|---|
| normal, debout ou allongé | 0,0202 – 0,0203 | ±1 % |
| pendant un relèvement | 0,0182 | −10 % |
| **lidar bloqué (14:14:44)** | **0,0334** | **+64 %** |
| **lidar bloqué (13:55:59)** | **0,0114** | **−44 %** |

Le seuil de 25 % sépare donc nettement le blocage du pire cas normal.

> ⚠️ **Le blocage se manifeste dans les deux sens.** Une première version ne
> regardait que la *baisse* de rotation : elle a détecté le blocage de
> 13:55, mais laissé passer celui de 14:14 (où la rotation **monte**). Le
> chien est resté allongé, le lidar bloqué. C'est corrigé, et un test
> verrouille les deux formes.

> ⚠️ **La médiane, et non le maximum.** Une mesure anormale a été relevée
> pendant une pose (0,0729, soit 3,6 fois la normale). Avec une échelle
> bâtie sur le maximum, tout le reste de la session aurait semblé « bloqué »
> et le chien se serait relevé à chaque « se coucher » : c'est exactement ce
> qui est arrivé. Un test verrouille ce cas.

> ⚠️ **Seules les mesures normales entrent dans l'historique.** Sans cela, un
> blocage durable décalerait la référence, et le détecteur s'éteindrait de
> lui-même au bout de quelques secondes. Un test verrouille ce cas aussi.

> ⚠️ Le `dirty_percentage` du lidar **n'est pas** un indice de blocage :
> il passe de 0-8 % (debout) à 61-70 % (allongé) alors que le lidar tourne
> librement. Un premier jet s'appuyait dessus : c'était faux, le
> déclenchement a été corrigé.

**Limites assumées**

- Un robot **tombé** n'est pas relevé : le cas visé est le bloc « se coucher ».
  Un adulte s'en occupe.
- Le relevé est une **manœuvre physique** : il échoue si l'espace autour du
  robot est obstrué. Le chien reste allongé, et l'interface le dit.
- Si le robot est **porté** pendant l'opération, l'arrêt de sécurité de
  portage est prioritaire : son verrouillage interdit tout relevé.

> ⚠️ **Deux blocages réels ont été observés** sur le robot le 21/10/2026,
> et ils n'ont pas la même signature : l'un fait chuter la rotation du
> lidar (−44 %), l'autre la fait monter (+64 %). Le seuil de 25 % est calé
> sur ces deux mesures, mais deux échantillons ne prouvent pas la marge : il
> faudra le confirmer sur d'autres blocages. Voir `docs/ROBOT_SETUP.md`.

**La fenêtre de grâce des postures**

Un changement de posture volontaire (« s'asseoir », « se coucher », « se
relever ») décharge les pieds avant que le robot ne publie sa nouvelle
posture. Pendant les **5 secondes** qui suivent la commande, la détection de
portage est donc **suspendue** : un robot qui s'assoit n'est pas pris pour un
robot soulevé. C'est cette fenêtre qui évite le faux arrêt du 21/10/2026.

Conséquence : soulever le robot pendant un changement de posture ne déclenche
rien pendant 5 s. En dehors de cette fenêtre, la détection est active.

**Réarmement**

Le verrouillage ne s'enlève que lorsque les quatre pieds portent de nouveau
pendant **une seconde**. Un seul échantillon favorable ne suffit pas.

La posture n'est pas exigée : après un `Damp`, le robot peut être allongé. Le
programme suivant le relèvera. Si ses pieds ne portent pas (robot sur le
flanc, par exemple), le réarmement automatique ne s'applique pas : un adulte
doit reconnecter le robot.

Aucun programme n'est repris automatiquement après un arrêt de sécurité.

**Limites assumées**

- Un seul pied au-dessus d'un vide, les trois autres portant, n'est **pas**
  détecté : `foot_force` ne dit pas où est le sol.
- Un robot posé au bord d'une table n'est pas détecté.
- Un robot soulevé alors qu'il est déjà assis ou allongé n'est pas détecté :
  ces postures sont exclues pour ne pas confondre un `Sit`/`Damp` volontaire
  avec un portage.
- Le détecteur ne distingue pas un portage d'une chute ou d'un robot posé sur
  un support sans appui : dans les deux cas, `Damp` relâche les pattes. Un
  robot non soutenu peut donc tomber.
- Sans `foot_force` frais, aucun portage n'est conclu. Une mesure absente
  n'est jamais remplacée par une valeur favorable.
- `rt/lf/lowstate` est un flux basse fréquence : la détection arrive au
  prochain message, soit environ **0,5 s** après le décollage. Les pattes
  peuvent donc bouger brièvement avant le `Damp`.
- Le verrouillage est **en mémoire** : un redémarrage du service l'efface.
  Après un redémarrage, un adulte doit vérifier que le robot est au sol avant
  de relancer un programme.
- Cette protection ne remplace ni la télécommande, ni l'adulte, ni l'arrêt
  d'urgence physique.

> ⚠️ **Portage réel non validé à ce jour.** Les tests couvrent la décision
> pure, l'adaptateur (topics simulés), le moteur et le chien de garde. Les
> transitions « s'asseoir » et « se relever » ont été essayées sur le robot ;
> aucun essai de soulèvement n'a été lancé dans le cadre de cette
> modification.

### Le bail en détail

```
frontend                          service
  │ POST /start                     │
  │ ───────────────────────────────▶ │
  │                                 │ moteur lancé, bail armé
  │ POST /heartbeat  (toutes 500ms) │
  │ ───────────────────────────────▶ │ bail renouvelé
  │                                 │
  │  ✖ interface fermée / réseau    │
  │     coupé / onglet planté       │
  │                                 │ 1,5 s plus tard → ARRÊT
```

C'est la protection principale contre la disparition du frontend. Elle est
testée dans les deux sens : battements → aucun arrêt, absence de battements →
arrêt.

> **Bug réel rencontré pendant le développement :** le frontend envoyait
> `{"runId": ...}` alors que le service attendait `{"run_id": ...}`. Tous les
> battements étaient refusés en 422, le bail expirait, et le chien de garde
> **arrêtait le robot au bout de 1,5 s**. La protection a donc détecté un vrai
> défaut de contrat. C'est le comportement attendu, et c'est verrouillé par un
> test de non-régression (`TestHeartbeatContract`).

---

## 5. Valeurs autorisées

Toutes dans `shared/safety-limits.json`.

| Paramètre | Valeur | Origine |
|---|---|---|
| Vitesse linéaire | 0,3 m/s (plafond dur) | `Move(0.3,0,0.3)` dans l'exemple officiel |
| Vitesse angulaire | 0,5 rad/s | `Move(0,0,0.5)` dans l'exemple officiel |
| Distance par pas | 5 – 200 cm | choix pédagogique |
| Angle par pas | 15 – 180° | choix pédagogique |
| Attente | 0,1 – 10 s | choix pédagogique |
| Répétitions | 20 | choix pédagogique |
| Programme | 500 pas, 120 s | choix pédagogique |
| Distance totale | 1500 cm | choix pédagogique |
| Rotations totales | 3600° | choix pédagogique |
| Tolérance de fin | 5 cm / 8° | **à confirmer sur robot réel** |
| Délai de déplacement | nominal × 2,5 + 1 s | garde-fou anti-blocage |

> ⚠️ Les tolérances et le délai de sécurité sont des **choix d'ingénierie non
> validés sur robot**. Ils doivent être confirmés (ou révisés) après la campagne
> physique, avec un adulte responsable présent et vigilant.

### Ces valeurs sont-elles modifiables depuis l'interface ?

Les dix premières valeurs **le sont**, via le panneau Configuration. Trois
garanties s'y appliquent :

| Garantie | Mécanisme |
|---|---|
| Plafond non franchissable | `config.HARD_CEILINGS`, figé dans le code Python |
| Un adulte doit confirmer | mot « RÉGLAGES » + autorisation explicite |
| Refus pendant l'exécution | HTTP 409 si un programme tourne |

Un adulte peut donc **ralentir** le robot pour une classe d'âge, jamais
l'accélérer au-delà de la valeur livrée. Le tableau ci-dessus représente les
**plafonds**, pas les valeurs par défaut.

> Relever un plafond exige de modifier `config.py` puis de redémarrer le
> service : un acte visible en revue de code, impossible pendant une séance.

---

## 6. Honnêteté des retours

L'interface ne présente **jamais** une action comme réussie sans confirmation.

| Situation | Affichage |
|---|---|
| cible atteinte d'après l'état mesuré | « mesuré · 45 cm » |
| consigne envoyée, aucun retour du SDK | « terminé » |
| délai atteint sans confirmation | « temps écoulé (non mesuré) » |
| interrompu sur demande | « arrêté » |

Une posture (« Se mettre debout ») **n'a pas** de confirmation mesurée par le
SDK : elle affiche « terminé », **pas** « mesuré ».

Si le retour de position n'est pas exploitable, tous les déplacements se
solderont par « temps écoulé ». C'est acceptable, et c'est honnête.

---

## 7. Ce que le logiciel ne fait PAS

- Il ne **garantit pas** l'arrêt physique du robot.
- Il ne remplace **pas** la télécommande officielle.
- Il ne dispense **pas** de la surveillance d'un adulte.
- Il n'empêche **pas** le robot de tomber ou de glisser.
- Il ne certifie **pas** la précision d'un déplacement.

---

## 8. Activités interdites en usage pédagogique

Volontairement absentes de l'application :

- sauts, flips, acrobaties (`FreeJump`, `LeftFlip`, `BackFlip`, `HandStand`,
  `CrossStep`, `WalkUpright`, `FreeBound`, `FreeWalk`) ;
- commande **bas niveau** des moteurs (`rt/lowcmd`, CRC32) — un test vérifie
  son absence dans le code ;
- modification des paramètres de sécurité du robot ;
- « Répéter indéfiniment » : les programmes sont bornés dans le temps et en
  nombre d'étapes.

---

## 9. Procédure d'urgence

### Le robot bouge alors qu'il ne devrait pas

1. **Télécommande** : bouton d'arrêt, immédiatement.
2. **Arrêt physique** du robot.
3. Couper l'alimentation si nécessaire.
4. Attendre que le robot soit **immobile** avant d'intervenir.
5. Ne pas toucher au robot tant qu'il n'est pas complètement arrêté.
6. Vérifier la zone, réparer la cause, puis relancer l'essai **avec un adulte**.

### L'interface affiche « Sécurité : le service a arrêté le robot »

Le service a déclenché l'arrêt de sécurité (bail expiré ou erreur). Le robot
devrait être immobile. Vérifier physiquement avant de relancer.

### Le robot est soulevé : « il s'est arrêté et a relâché ses pattes »

C'est la protection de portage. Le robot a reçu `Damp` : il est **mou**, il ne
tient pas tout seul.

1. Le poser **doucement** au sol, en le tenant.
2. Attendre **une seconde** : le service réarme quand les quatre pieds
   portent.
3. S'il reste allongé et que le bandeau reste affiché, un adulte doit
   **reconnecter** le robot (bouton « Robot réel »), puis relancer un
   programme : il se relèvera tout seul.
4. Ne jamais poser les doigts entre les pattes d'un robot mou.

> ⚠️ Tant que le `Damp` de portage n'a pas été essayé sur le robot réel
> (aucun essai de soulèvement n'a été autorisé), cette procédure est
> **théorique** : la télécommande reste la référence.

### Le service ne répond plus du tout

1. Arrêt physique du robot.
2. Arrêter le service.
3. Le chien de garde a dû agir : c'est le but.
4. Si le robot a continué à marcher, **c'est un défaut de sécurité à signaler**
   et `docs/ROBOT_SETUP.md` doit être suivi **sans délai**.

---

## 10. Règles pour les sessions avec les enfants

### Avant

- [ ] Zone dégagée sur au moins **3 m** dans tous les sens
- [ ] Aucun câble, cartable ou meuble à portée du robot
- [ ] Télécommande chargée et à portée de main de l'adulte
- [ ] **Un adulte dans la pièce**, qui regarde le robot — pas l'écran
- [ ] Mode **simulation** pour la découverte
- [ ] Batteries en charge suffisante

### Pendant

- [ ] Un seul programme à la fois
- [ ] Rester **derrière** le robot, jamais devant son chemin
- [ ] Bouton « Arrêter » accessible sans changer de fenêtre
- [ ] Arrêter immédiatement si le robot fait quelque chose d'inattendu

### Après

- [ ] Ranger et éteindre proprement
- [ ] Signaler tout comportement étrange à l'équipe informatique

---

## 11. Exposition réseau

Par défaut, le service écoute sur **`127.0.0.1`** : uniquement la machine qui
l'exécute peut le joindre.

- Ne **jamais** l'exposer sur Internet.
- Pour un accès depuis un autre poste, ce n'est **pas** encore prévu pour un
  usage pédagogique.
- Le service **n'est pas authentifié** : il fait confiance au réseau local.
- Le WebSocket vérifie l'origine (`Origin`) contre une liste blanche.

Si une exposition réseau devient nécessaire, il faudra ajouter au minimum :
authentification, liste blanche d'adresses IP, et journalisation des commandes.

---

## 12. Journalisation

Le service journalise :

- démarrage et arrêt ;
- refus de changement de mode ;
- déclenchements du chien de garde (`WARNING`) ;
- erreurs d'exécution.

Les battements et l'état ne sont **pas** journalisés : trop volumineux et sans
intérêt pédagogique. Aucun nom d'enfant n'est journalisé : il n'y en a pas.

---

## 13. Checklist avant d'ouvrir une session

1. Lire `docs/USER_GUIDE.md`.
2. Vérifier l'état d'avancement du `README.md`.
3. Si le mode réel est utilisé : lire `docs/ROBOT_SETUP.md` et vérifier que la
   campagne physique est terminée et consignée.
4. Confirmer que `shared/safety-limits.json` n'a pas été modifié sans
   validation.
5. Faire une session en **simulation** avant toute session avec le robot.