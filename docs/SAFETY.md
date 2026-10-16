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
| Vitesse linéaire | 0,3 m/s | `Move(0.3,0,0.3)` dans l'exemple officiel |
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