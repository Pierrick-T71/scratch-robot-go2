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
  - En cliquant sur le bouton « Sauvegarder » (icône disquette d'origine dans la barre supérieure), le programme est immédiatement sérialisé en JSON et téléchargé dans le dossier **Téléchargements** du PC hôte (`programme-go2.json`), tout en conservant une copie miroir dans le `localStorage` local.
- **Importation 2-en-1 directement intégrée dans la Dropzone** :
  - **Barre supérieure restaurée à l'identique visuellement** (Mode manuel, Mode autonome, Sauvegarder).
  - Le grand bloc central en pointillés de la timeline affiche désormais :  
    *« Glisser-déposer le fichier ou les blocs ici pour programmer »*.
  - **Au clic** sur ce bloc : ouvre directement le sélecteur de fichier de votre PC hôte pour choisir un fichier `.json`.
  - **Au glisser-déposer** : vous pouvez glisser un fichier `.json` depuis votre explorateur directement dans la dropzone (ou continuer à y déposer des blocs de la bibliothèque).
- **Compatibilité Totale avec les Blocs Futurs** :
  - Le parseur `parseBlocksFromJson` et le modèle `PlayBlock` préservent l'ensemble des clés et paramètres personnalisés (`[key: string]: unknown`).
  - Tolérance aux blocs futurs dans `specOfOrFallback` pour afficher tout futur bloc sans rupture.
  - Rétro-compatibilité assurée avec les formats de déclarations backend (`statements`).

---

## 9. Nettoyage Interface, Enchaînement d'Actions Mobile & Corrections Simulation

**Date :** 29/10/2026

### 9.1. Annulation Réactive des Postures et Actions sur Mobile (`MobileGamepad.svelte`)
- **Problématique résolue** : Sur mobile, lorsqu'on ordonnait une posture (ex. s'asseoir) puis qu'on demandait un saut ou un mouvement au joystick, le robot se rasseyait immédiatement à cause d'anciennes actions ou d'un statut en retard.
- **Correctifs** :
  - Mécanisme d'annulation immédiate `cancelRunningAction()` lors de tout nouvel ordre ou mouvement au stick.
  - Dérivation de posture dynamique : dès qu'un mouvement de joystick ou un saut survient, la posture assise/couchée est rompue et repasse à `STAND`.
  - Jetons de séquence d'action (`#actionSeq`) dans `app.svelte.ts` pour ignorer les réponses `refreshStatus()` périmées arrivant après une commande utilisateur.
  - Synchronisation de l'animation 3D sur le saut manuel (`manualAction`).

### 9.2. Corrections Mode Simulation & Clavier (`simulated.py` & `ManualPanel.svelte`)
- **Saut clavier (Espace) et boutons** :
  - Déclenchement garanti avec support multi-claviers (`Space`, `Spacebar`, ` `).
  - En simulation (`simulated.py`), le saut manuel applique désormais un bond franc de +50 cm vers l'avant et réinitialise la posture à `STAND`.
- **Réactivité ZQSD / Flèches** :
  - Support normalisé pour ZQSD, WASD et flèches directionnelles.
  - Réinitialisation de la posture à `STAND` lors de toute commande de vitesse manuelle ou déplacement.

### 9.3. Éradication du Panneau de Réglages Superflu
- **Suppression du bouton ⚙️ et de la modale Réglages** :
  - Retrait du bouton outil dans `BlockLibrary.svelte` et de la modale associée dans `App.svelte`.
  - L'interface reste 100% dédiée à l'enfant, sans menus de configuration inutiles.
- **Garantie de Sécurité Intégrée** :
  - Les limites de sécurité physique restent strictement vérifiées côté serveur via `config.HARD_CEILINGS` (vitesse max 0,5 m/s, plafonds d'angles et distances).
  - Mise à jour du `README.md` reflétant la simplification de l'interface et l'autorité native du backend.

---

## 10. Recentrage Automatique au Rechargement & Déblocage Exécution Simulateur

**Date :** 29/10/2026

### 10.1. Recentrage au Rechargement de Page (Refresh F5)
- **Nettoyage automatique au montage (`initPageRefresh`)** :
  - Dès le montage de l'application (`App.svelte` / `onMount`), `app.initPageRefresh()` arrête tout mode manuel résiduel et ordonne un recentrage complet en simulation.
  - Utilisation de `keepalive: true` sur `/api/manual/stop` et `/api/execution/stop` dans `client.ts` pour garantir la transmission réseau même en cas de fermeture ou rafraîchissement brusque de la page du navigateur.
  - Câblage de l'événement Three.js `recentrer()` via `resetSimulationTrigger` synchronisé entre le store `app.svelte.ts`, `RobotStage.svelte`, `MobileGamepad.svelte` et `LidarScene.svelte` : le modèle 3D du robot revient immédiatement au centre (0, 0, 0), son cap est remis à zéro, et la caméra se repositionne immédiatement derrière lui.

### 10.2. Déblocage du Mode Manuel Résiduel sur Simulateur
- **Suppression du refus HTTP 409 intempestif** :
  - Dans `main.py` (`/api/execution/start`), le blocage qui levait l'erreur *« Quitte d’abord le mode manuel avant de lancer un programme »* a été remplacé par un arrêt automatique et propre du mode manuel (`await state.manual.stop()`), aligné sur le comportement du mode autonome.
  - Dans `/api/simulation/reset`, le mode manuel est également arrêté automatiquement pour éviter tout état fantôme.
- **Garantie de Déplacement Simulateur** :
  - Dans `simulated.py` (`_do_move`), la posture est remise à `STAND` et l'état à `MOVING` pour assurer que le robot avance systématiquement même s'il était préalablement assis ou couché.

---

## 11. Résolution Affichage Erreurs & Fiabilisation Contrôleur Smartphone

**Date :** 29/10/2026

### 11.1. Visibilité des Erreurs et Avertissements sur Smartphone
- **Bannière d'alerte rouge haute visibilité (`.mobile-error-toast`)** :
  - Ajout d'une bannière rouge vif (`#dc2626`) flottant au sommet de la vue paysage du smartphone avec l'icône `🛑`.
  - Affiche instantanément les erreurs de blocage de mouvement, échecs d'actions, alertes de sécurité et déconnexions du service robot.
  - Auto-fermeture au bout de 4 secondes et bouton de fermeture immédiate (✕).

### 11.2. Fiabilisation de la Connexion et Déblocage des Actions Mobile
- **Éradication de la condition de course à l'ouverture (`?remote=1`)** :
  - `App.svelte` n'appelle plus `initPageRefresh()` si `isRemoteMode` est actif, évitant de fermer le mode manuel au moment même où le téléphone l'ouvre.
  - Dans le store (`app.svelte.ts`), `actionManual`, `jumpManual` et `moveManual` vérifient l'état `manualActive` et auto-démarrent le mode manuel si nécessaire avant l'envoi de la consigne.
- **Maintien de la connexion en tâche de fond** :
  - Ajout d'un cycle de rafraîchissement d'état régulier à 2 secondes dans `MobileGamepad.svelte`.
  - Reconnexion et réouverture automatique de session manuelle dès le retour au premier plan ou réveil d'écran (`visibilitychange: visible`).

### 11.3. Clarification et Suppression du Bouton « Faire le beau »
- **Origine** : Ce bouton correspondait à l'ancienne commande SDK interne `balance` qui n'a aucun équivalent dans les blocs de programmation Scratch, ne possède aucune animation 3D et n'est pas gérée par le vrai Go2.
- **Harmonisation** : Suppression du bouton orphelin. Le pavé gauche regroupe désormais les 3 vraies postures Scratch parfaitement alignées sous le joystick : Se mettre debout (`stand`), S'asseoir (`sit`), Se coucher (`lie_down`).
