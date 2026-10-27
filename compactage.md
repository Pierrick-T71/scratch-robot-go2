# Compactage des Développements - Go2 Play

**Dernière mise à jour :** 27/10/2026 10:45 (Europe/Paris)

---

## 1. Contexte & Réseau
- **Hôte / Conteneur de service** : `172.16.13.41`
  - Backend FastAPI (`go2_service`) : port `8765`
  - Frontend Vite (`vite preview`) : port `5173`
- **Robot Unitree Go2 Pro réel** : `172.16.8.11`
  - Connexion WebRTC active via le canal de données (DataChannel WebRTC 9991) et le protocole sécurisé Unitree (`rt/sportmod`, `rt/utlidar/switch`, `rt/api/vui/request`).
  - Statut en ligne vérifié et testé en conditions réelles : `connected: true`, mode `real`.
  - Contrôle manuel débridé et réactif : vitesse d'avance à 0,6 m/s, vitesse de rotation à 1,0 rad/s (~57°/s).

---

## 2. Mode Manuel : Clavier PC & Manette Mobile Plein Écran

### 2.1. Grand Rectangle Intégré PC (Clavier à gauche + QR Code à droite)
- **Suppression du bouton pop-up** : Le bouton qui ouvrait une modale séparée a été retiré de l'en-tête de `ManualPanel.svelte`.
- **Affichage direct 2-en-1 dans un grand rectangle (`manual__grid`)** :
  - **Volet gauche (Touches Clavier PC)** :
    - Touches Z (avancer), S (reculer), Q (pas à gauche), D (pas à droite).
    - Touches fléchées gauche et droite (rotation fine).
    - Barre Espace (saut manuel immédiat).
    - Légende interactive et retour visuel d'activation.
  - **Volet droit (Contrôle Smartphone)** :
    - QR Code haute visibilité généré directement à l'écran via `qrcode` (170x170 px).
    - Adresse réseau local réelle garantie (`http://172.16.13.41:5173/?remote=1`), **jamais `localhost`**.
    - Boîte URL avec bouton « Copier » en un clic.
    - Accès immédiat par simple scan avec l'appareil photo du smartphone connecté au même Wi-Fi.

### 2.2. Manette Mobile Plein Écran & Optimisation iPhone (`MobileGamepad.svelte`)
- **Adaptation spéciale iPhone 16 & Safari iOS** :
  - `viewport-fit=cover` ajouté dans `index.html` pour étendre l'affichage sur toute la dalle.
  - Prise en compte rigoureuse des marges de sécurité iOS (`env(safe-area-inset-bottom)`, `top`, `left`, `right`) pour que les contrôles ne soient jamais masqués par la Dynamic Island ou la barre d'accueil d'iOS.
  - Utilisation de `100dvh` (Dynamic Viewport Height) pour s'adapter exactement à l'espace visible avec ou sans barres de navigation Safari.
  - Hauteur du viewport 3D auto-adaptative (`flex: 1 1 0; min-height: 0`), garantissant que le **bouton Sauter (34 px)** reste **100% visible et accessible** au bas de l'écran sans aucun défilement.
  - Dimensions compactées des joysticks (diamètre 108 px, knob 44 px, rayon max 36 px) calibrées pour les hauteurs d'écran paysage sur smartphone.
- **Mode Plein Écran (Cacher l'URL et les onglets)** :
  - Bouton **« Plein écran »** intégré dans la barre d'outils supérieure de la scène centrale.
  - Déclenche l'API Fullscreen native (`requestFullscreen()` / `webkitRequestFullscreen()`) sur les navigateurs le supportant.
  - Sur iOS Safari (qui restreint l'API Fullscreen pour les éléments Web), affichage d'un toast d'astuce explicite :
    *« Touchez Partager ⎋ puis "Sur l'écran d'accueil ⊞" pour masquer totalement l'URL et les onglets ! »*.
  - Balises PWA Apple intégrées (`apple-mobile-web-app-capable: yes`, `apple-mobile-web-app-status-bar-style: black-translucent`) permettant un affichage 100% plein écran natif sans aucune barre de navigateur lors de l'ouverture depuis l'écran d'accueil.
- **Joysticks tactiles** :
  - **Joystick gauche 2D complet (ZQSD)** : Avance/Recul (Z/S) sur l'axe vertical, pas chassé gauche/droite (Q/D) sur l'axe horizontal.
  - **Joystick droit** : Rotation/pivot gauche et droite.
  - **Combinaisons twin-stick** prises en charge.
  - **Vue LiDAR 3D & Caméra** commutables instantanément.

### 2.3. Sécurité, Arbitrage et Watchdog TTL
- **Arbitrage des sources (`keyboard` vs `mobile`)** :
  - Suivi distinct des séquences (`seq`) par source dans `ManualControl`.
  - Quand une source pilote activement dans la limite du bail (`MANUAL_TTL_S = 2.0 s`), les commandes concurrentes de l'autre source sont bloquées avec message explicite.
  - Dès relâchement des commandes (`direction: null`), le verrou est libéré immédiatement.
- **Sécurité réseau & Arrêt immédiat** :
  - Relâchement tactile, verrouillage d'écran ou changement d'onglet (`blur`, `visibilitychange`) déclenchent l'arrêt immédiat (`direction: null`).
  - En cas de coupure Wi-Fi du téléphone, le watchdog TTL de 2,0 s côté service stoppe automatiquement le robot.

---

## 3. Résolution des Rotations des Blocs (Fin des tours à 180° et retournements)

### 3.1. Diagnostic Technique
- **Symptôme** : Un bloc de rotation à 90° tournait à ~136°–180°, parfois le robot pivotait indéfiniment ou se retournait complètement.
- **Cause racine 1 (Condition d'arrêt)** : Dans `_tourner`, la condition d'arrêt était strictement `abs(ecart) <= YAW_BANDE_MORTE_DEG` (1.0°). À 1,2 rad/s, les pas discrets d'un quadrupède de 12 kg (sauts de ~2° à 3°) et les intervalles de rafraîchissement WebRTC franchissaient la bande morte d'un coup (passage direct de +1,5° à -1,5°). `abs(ecart) > 1.0` restait vrai, commandant une inversion de sens (`math.copysign(vitesse, ecart)`). Le robot oscillait violemment d'avant en arrière jusqu'au timeout de sécurité (6,3 s), aboutissant à ~180° ou à un demi-tour incontrôlé.
- **Cause racine 2 (Saturation CPU par le LiDAR)** : Le callback `_sur_lidar` décodait un maillage de plus de 827 000 éléments dans des boucles Python synchrones sur le thread asyncio principal (`_cellules_2d` et `_maillage_3d`). Ce traitement bloquait l'event loop pendant 3 à 4 secondes consécutives, induisant un décalage massif entre la position angulaire réelle du robot et la valeur lue par le service.

### 3.2. Corrections Apportées
- **Arrêt franc et directionnel** :
  - Arrêt dès pénétration dans la bande morte OU franchissement de la cible dans la direction commandée :
    `if abs(ecart) <= YAW_BANDE_MORTE_DEG or (signe > 0.0 and ecart <= 0.0) or (signe < 0.0 and ecart >= 0.0): break`
  - Élimine tout demi-tour résiduel et toute oscillation pendulaire.
- **Fréquence adaptative & freinage progressif** :
  - Câblage à 20 Hz (50 ms) dès que l'écart restant < 25°.
  - Décélération progressive via `yaw_rate_for_remaining(abs(ecart), min(vitesse_max, 1.0))` garantissant une arrivée en douceur.
- **Priorité absolue au mouvement (Bypass LiDAR)** :
  - Pendant un mouvement (`self._state == RobotState.MOVING`), le traitement synchrone du maillage lourd du LiDAR est court-circuité. La boucle asyncio conserve 100% de ses cycles pour le rafraîchissement d'orientation et les consignes de vitesse à 50 Hz.

### 3.3. Validation sur Robot Réel (`172.16.8.11`)
- **`turn_left 90°`** :
  - Exécution en **3,24 s** (contre 6,3 s de timeout auparavant).
  - Delta mesuré : **+92,68°** (écart < 2,7° par rapport à la cible, correspondant au pas discret des pattes).
  - Arrêt net et propre, résultat `"exact"`, aucune oscillation.
- **`turn_right 90°`** :
  - Exécution en **2,58 s**.
  - Delta mesuré : **-84,27°** (écart ~5,7°).
  - Arrêt franc, aucun retournement.

---

## 4. Gestion Intelligente du LiDAR, Posture & Thermique en Veille

### 4.1. Relèvement Préalable sur 4 Pattes Avant Coucher
- **Sécurité de posture** : Avant d'exécuter `StandDown` (1005), le service vérifie systématiquement si le robot est debout sur ses 4 pattes (`_est_debout()`).
- Si le robot est assis (`SIT`) ou dans une autre posture, il commande d'abord `StandUp` et attend qu'il soit debout et stable.
- Cette étape garantit une descente `StandDown` parfaitement symétrique, avec pliage synchronisé des 4 pattes et atterrissage à plat sans bascule.

### 4.2. Arrêt / Redémarrage du Moteur LiDAR en Veille
- **Entrée en veille (`enter_standby`)** :
  - Une fois au sol, il envoie la commande d'extinction `publish_without_callback("rt/utlidar/switch", "OFF")` (avec doublon `"off"` pour compatibilité) et désabonne les flux.
  - Le moteur/miroir LiDAR est ainsi arrêté pendant toute la durée de la veille.
- **Sortie de veille (`exit_standby`)** :
  - Le LiDAR est immédiatement redémarré en envoyant `publish_without_callback("rt/utlidar/switch", "ON")` (et `"on"`), et les flux sont réabonnés.
  - Le robot se relève (`StandUp`) et reprend la main.

### 4.3. Gestion Thermique & Ventilateurs en Veille
- **Télémétrie thermique active** : Le service lit en continu les sondes de température de `rt/lf/lowstate` (`temperature_ntc1` pour la carte mère/châssis, et le tableau des températures moteurs `motor_state`).
- **Contrôle matériel des ventilateurs** :
  - Le SDK officiel Unitree stipule explicitement : `fan[2]; // It has been changed to internal control and is currently not used`.
  - Il n'existe pas de commande logicielle externe pour forcer l'extinction des 3 ventilateurs (protection matérielle anti-surchauffe du SoC et des cellules de batterie).
  - En revanche, la mise en veille supprime les sources thermiques : le corps posé au sol annule les efforts de maintien des 12 moteurs (chute du courant) et l'arrêt du LiDAR décharge le CPU.
  - Dès que la température interne descend sous la courbe de consigne du MCU (~45°C), le firmware interne ralentit et coupe automatiquement les ventilateurs.

### 4.4. Maintien Éveillé en Fonctionnement (Mode Sécurité)
- En fonctionnement normal (robot actif / debout), tant que le mode sécurité est actif (`obstacle_safety_enabled == True`), le LiDAR n'est **jamais coupé par la temporisation d'inactivité de 15 s**.

---

## 5. Retrait Définitif du Mode Déplacement « Avancer accroupi » (Crawl / Creep Gait)

### 5.1. Bilan Technique & Décision de Retrait
- **Limites Matérielles Validées sur Go2 Réel (`172.16.8.11`)** :
  - L'appel RPC `BodyHeight` (api_id 1013) renvoie l'erreur `code: 3203` (*« API not implemented on server »*), cette fonction n'existant que sur les robots B2/A2.
  - La démarche `StaticWalk` (api_id 1061) modifie uniquement la phase de pose des pattes (démarche 4 temps), mais ne fléchit pas les genoux ni n'abaisse le châssis, qui demeure à sa garde au sol normale (~32 cm).
  - Aucune commande haut niveau Go2 ne permet une marche accroupie effective sans passer par un asservissement bas niveau DDS à 500 Hz (incompatible avec le contrôle Wi-Fi/WebRTC pour des raisons de gigue et de sécurité).
- **Suppression Complète du Bloc et de la Chaîne d'Exécution** :
  - **Interface & Éditeur Visuel** : Retrait du bloc « Avancer accroupi de » (`crawl_forward`) de la palette de blocs (`blocks.ts`).
  - **Modèle de Programme & Validation** : Suppression de `CrawlStatement` (`program.ts`), des règles de validation associées (`validate.ts`), et des assertions dans les tests (`play-blocks.test.ts`).
  - **Catalogue Scratch stabilisé à 12 blocs** :
    - *Mouvement (4)* : Avancer de [N] s, Reculer [N] s, Tourner à gauche de [N]°, Tourner à droite de [N]°.
    - *Actions (8)* : S’asseoir, Se lever, Garder l’équilibre, Se coucher, Faire un cœur, Faire un saut, Saluer, S’étirer.
  - **Service Backend (`robot-service`)** :
    - Retrait de `CrawlStatement`, `CommandKind.CRAWL_FORWARD` et `CommandKind.CRAWL_BACKWARD`.
    - Nettoyage dans `interpreter.py`, `validation.py`, `motion.py`, `obstacles.py` et les adaptateurs (`simulated.py`, `webrtc.py`).
    - Élimination des tests unitaires obsolètes dans `test_validation.py`.

---

## 6. Mode Autonome Fluide, Évitement d'Obstacles à 30 cm & Comportements Canins

### 6.1. Démarrage Instantané & Seuil d'Arrêt Réel à 30 cm
- **Démarrage instantané sans blocage** :
  - Sur le Go2 réel en WebRTC, `FreeAvoid` (2048) est envoyé en mode asynchrone non-bloquant `_envoyer_sans_reponse("FreeAvoid", json.dumps({"data": True}))`. Le robot démarre immédiatement sans attendre 5 secondes de timeout.
- **Calibrage géométrique du seuil d'obstacle (`OBSTACLE_THRESHOLD_M = 0.65 m`)** :
  - `free_distance_m` mesure la distance depuis le **centre géométrique du robot** (`rx, ry`).
  - Le museau du chien se situe à **+35 cm** en avant du centre, avec une marge de case de 5 cm (`dist_museau = clearance - 0.30 m`).
  - À `0,45 m`, la distance réelle devant le museau n'était que de 15 cm : avec l'inertie de freinage et la période de traitement LiDAR (0,5 s), le robot heurtait les murs avant de pouvoir s'arrêter.
  - À `0,65 m`, le robot déclenche l'arrêt net à **exactement 30-35 cm du mur**, s'immobilise sans le toucher, et dispose de tout le rayon de dégagement nécessaire (38 cm de diagonale de rotation) pour pivoter sans frotter.

### 6.2. Changement de Direction et Contournement d'Obstacles
- Dès qu'un obstacle est détecté à ~30 cm devant :
  1. **Arrêt immédiat** : Vitesse nulle envoyée (`manual_velocity("forward", speed_mps=0.0)`).
  2. **Analyse des dégagements gauche/droite** : Interrogation simultanée de `clearance_m("left")` et `clearance_m("right")`.
  3. **Pivot vers le côté le plus ouvert** : Rotation de ~70° à 0,8 rad/s (1,5 s) vers la direction la plus dégagée (`turn_left` ou `turn_right`).
  4. **Vérification d'angle & anti-coin** : Si après le premier pivot la voie est encore barrée (ex. coin de mur), il effectue une rotation complémentaire (~55°) dans le même sens.
  5. **Reprise de l'exploration** : Dès que l'horizon est dégagé, le robot reprend sa marche avant fluide à 0,25 m/s.
  6. **Gestion des impasses totales** : Si et seulement si après 3 tentatives de pivot le passage reste totalement bloqué dans toutes les directions, le mode autonome s'arrête avec le message d'erreur :
     *« Espace bloqué : impossible de trouver une issue après pivot. »*

### 6.3. Comportements Canins Aléatoires (« Comme un Vrai Chien »)
- Toutes les 20 à 35 secondes de marche autonome libre, le robot marque une pause vivante :
  1. **S'étirer** (`Stretch`) : Le robot s'étire vers l'avant puis reprend sa balade.
  2. **S'asseoir et observer** (`Sit` + pause 4 à 7 secondes + `StandUp`) : Le robot s'assoit, regarde autour de lui quelques secondes, puis se remet sur ses pattes.
  3. **Saluer de la patte** (`Salute`) : Coucou amical de la patte avant.
- Une demande d'arrêt (carré rouge Scratch ou bouton mode autonome) coupe immédiatement l'animation.

### 6.4. Verrouillage de la Sécurité LiDAR & Rafraîchissement Continu
- **Activation Automatique & Verrouillage de Sécurité** :
  - Dès l'activation du mode autonome, la sécurité obstacle (`obstacleSafetyEnabled`) est activée et l'interrupteur est grisé/verrouillé dans l'interface (`PlayHeader.svelte`).
  - L'API backend bloque toute tentative de désactivation pendant la navigation autonome (HTTP 409).
- **Maintien du Flux LiDAR en Mode Autonome** :
  - Dans l'adaptateur WebRTC (`webrtc.py`), le court-circuit du traitement LiDAR en déplacement est ignoré en mode autonome (`and not self._en_autonome`), assurant l'actualisation continue de la carte d'obstacles à 2 Hz.

---

## 7. Bilan des Tests et Statut Global
- **Backend Python (`robot-service`)** :
  - `python -m pytest robot-service/tests` : **358 / 358 tests validés (100%)**, incluant `test_posture.py` (transitions assis/couché).
- **Frontend Svelte / Vitest** :
  - `npm test` : **226 / 226 tests validés (100%)**, incluant les tests d'export / import JSON et tolérance aux blocs futurs.
  - `npm run check` : 0 erreurs et 0 avertissements diagnostics Svelte / TypeScript.
  - `npm run build` : Compilation de production Vite validée sans erreur.
- **Déploiement Conteneur `172.16.13.41`** :
  - Fichiers synchronisés et extraits dans `/root/go2/`.
  - Archives de déploiement actualisées : `dist.tgz` et `robot-src.tgz`.

---

## 8. Postures S'asseoir / Se Coucher, Relevage LiDAR & Sauvegarde JSON

### 8.1. Sécurisation des Transitions Postures (Assis <-> Couché)
- **Constat & Problématique** :
  - L'enchaînement d'un bloc « S'asseoir » suivi de « Se coucher » faisait basculer/tomber le robot car `CommandKind.LIE_DOWN` envoyait la commande de couchage directement depuis la position assise sans redresser le train arrière (`lever_si_assis` était à `False`).
  - L'enchaînement « Se coucher » suivi de « S'asseoir » échouait car le robot au sol ne peut pas physiquement s'asseoir sans se relever au préalable sur ses 4 pattes.
- **Correctif mis en place** :
  - Dans `webrtc.py` (`execute_command`) et `simulated.py` :
    - Avant `CommandKind.SIT_DOWN` : vérification stricte `if not self._est_debout(): await self._relever()`.
    - Avant `CommandKind.LIE_DOWN` : vérification stricte `if not self._est_debout(): await self._relever()` et `lever_si_assis=True`.
  - **Comportement optimisé** : Si le robot est déjà debout (par exemple après un bloc de marche « Avancer »), `self._est_debout()` est vrai et aucun ordre de relèvement superflu n'est envoyé ; le robot s'assied ou s'allonge directement. S'il est assis ou couché, il se remet d'abord sur ses 4 pattes pour garantir un mouvement fluide, symétrique et sans aucune chute.
  - **Validation unitaire** : 4 nouveaux tests automatisés dans `test_posture.py` (`TestTransitionsAssisCoucher`) couvrant les 4 cas de transition.

### 8.2. Vérification du Relevage Automatique lors du Blocage LiDAR au Sol
- **Mécanisme vérifié et confirmé opérationnel** :
  - `AutoRecovery` (`recovery.py`) et `_examiner_relever` (`webrtc.py`) surveillent en continu la rotation réelle du LiDAR (`rt/utlidar/lidar_state`).
  - Si le robot est au sol (`allongé=True`, `demande_par_nous=True`, `programme_en_cours=False`) et que la fenêtre tournante du LiDAR frotte le sol (écart rotation > 25% à la médiane ou `error_state != 0`) pendant plus de 0,6 s (`CONFIRM_S`), le robot commande automatiquement `StandUp` pour se remettre debout et préserver son matériel.
  - Statut exposé en temps réel vers le frontend via `recoveryReason`.

### 8.3. Nouveau Système de Sauvegarde & Importation JSON
- **Téléchargement direct sur PC Hôte** :
  - En cliquant sur « Sauvegarder », le programme est immédiatement sérialisé en JSON et téléchargé dans le dossier **Téléchargements** du PC hôte via un Blob déclenché (`programme-go2.json`), tout en conservant une copie miroir dans le `localStorage` local.
- **Réimportation en un clic (« Importer »)** :
  - Nouveau bouton ambré **« Importer »** dans la barre d'en-tête (`PlayHeader.svelte`), ouvrant un sélecteur de fichier `.json`.
  - Lecture et réhydratation instantanée du programme dans la timeline.
- **Compatibilité Totale avec les Blocs Futurs** :
  - Le parseur `parseBlocksFromJson` et le modèle `PlayBlock` préservent l'ensemble des clés et paramètres personnalisés (`[key: string]: unknown`).
  - Tolérance aux blocs futurs dans `specOfOrFallback` pour afficher tout futur bloc sans rupture.
  - Rétro-compatibilité assurée avec les formats de déclarations backend (`statements`).
