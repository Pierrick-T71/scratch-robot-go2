# TESTS — Inventaire et résultats

## 1. Résumé

| Suite | Commande | Résultat |
|---|---|---|
| Frontend — unitaires | `cd frontend && npm test` | **46 tests, 4 fichiers, tous passants** |
| Frontend — types | `cd frontend && npm run check` | **0 erreur, 0 avertissement** |
| Frontend — build | `cd frontend && npm run build` | **réussi**, aucun avertissement |
| Service — unitaires + intégration | `cd robot-service && python -m pytest -q` | **165 tests, tous passants** |

**Total : 225 tests automatisés.**

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
- Parcours d'interface dans un vrai navigateur

### ❌ NON testé — jamais

> **Aucune commande n'a été envoyée à un Unitree Go2.**

- Aucune connexion au robot.
- Aucun déplacement physique.
- Aucun test du comportement d'arrêt réel.
- Aucune mesure de précision.
- Aucun test de coupure réseau sur un robot réel.

L'adaptateur `UnitreeAdapter` est **écrit** d'après l'API officielle lue dans
le dépôt Unitree, mais il est **désactivé** (`physical_commands_enabled =
False`) et n'a jamais été exécuté.

Conséquence : le mode robot réel est **refusé par le service**, même si un
adulte l'autorise. C'est testé (`test_rejects_real_mode_even_with_authorisation`).

---

## 3. Tests frontend (60)

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

---

## 4. Tests du service (165)

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
- Récupération après erreur (pas de verrouillage)
- `request_stop()` appelé à la fin, même sur exception
- Chien de garde : pas de déclenchement sans exécution, pas avec battements,
  **déclenchement à l'expiration du bail**
- Arrêt d'urgence, mesure de l'âge du bail
- `StopSignal` : première raison conservée, réinitialisation

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
- Démarrage en simulation, état et capacités
- Mode réel refusé sans autorisation adulte
- **Mode réel refusé même AVEC autorisation** (adaptateur non validé)
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