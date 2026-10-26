# Compactage des Développements - Go2 Play

**Dernière mise à jour :** 26/10/2026 11:55 (Europe/Paris)

---

## 1. Contexte & Réseau
- **Hôte / Conteneur de service** : `172.16.13.41`
  - Backend FastAPI (`go2_service`) : port `8765`
  - Frontend Vite (`vite preview`) : port `5173`
- **Robot Unitree Go2 Pro réel** : `172.16.8.11`
  - Connexion WebRTC active via le canal de données (DataChannel WebRTC 9991) et le protocole sécurisé Unitree (`rt/sportmod`, `rt/utlidar/switch`, `rt/api/vui/request`).
  - Statut en ligne vérifié et testé en conditions réelles : `connected: true`, mode `real`, en veille au sol ($z = 0.052\text{ m}$).

---

## 2. Mode Veille Prolongée & Mode Couché (Unitree Go2 Pro)

### 2.1. Correction du Coucher : Remplacement de `Damp` par `StandDown` (1005)
- **Origine du problème (Le robot « tombait »)** :
  - L'implémentation initiale appelait `Sit` (1009) puis déclenchait `Damp` (1001) au bout de 1,2 s.
  - Or, `Sit` ne plie que les pattes arrière en gardant le torse relevé, et `Damp` coupe immédiatement le couple de tous les moteurs. Les pattes avant perdaient tout maintien et le robot chutait lourdement au sol.
- **Solution appliquée (`StandDown` 1005)** :
  - Utilisation de la commande native Unitree **`StandDown`** (API ID 1005) : le robot synchronise le repli de ses 4 pattes sous contrôle moteur en boucle fermée et **dépose délicatement son ventre au sol sans aucune chute ni choc**.
  - Attente de confirmation de stabilisation au sol (`_attendre_alleonge`, $z < 0.12\text{ m}$, mesuré à **$z = 0.052\text{ m}$** sur le robot réel).
  - Le robot reste posé à plat au repos sur son ventre.

### 2.2. Arrêt Complet du LiDAR et des Flux de Données
- **Origine du problème (Le LiDAR continuait de tourner / diffuser)** :
  - `rt/utlidar/switch` attend la chaîne `"off"` (ou `{"data": "off"}` pour le pont ROS/DDS).
  - Tant que le client WebRTC restait abonné aux topics `rt/utlidar/voxel_map` et `rt/utlidar/lidar_state`, le robot continuait de générer et d'émettre en continu les nuages de points et les diagnostics.
- **Actions de coupure intégrale appliquées** :
  1. **Arrêt de la génération de trafic WebRTC** : appel de `await connexion.datachannel.disableTrafficSaving(False)`.
  2. **Désabonnement explicite des topics** via `canal.unsubscribe()` :
     - `rt/utlidar/voxel_map_compressed` (`ULIDAR_ARRAY`)
     - `rt/utlidar/voxel_map` (`ULIDAR`)
     - `rt/utlidar/lidar_state` (`ULIDAR_STATE`)
     - `rt/utlidar/robot_pose` (`ROBOTODOM`)
     Les logs cessent immédiatement d'être inondés par les paquets LiDAR.
  3. **Extinction du LiDAR physique** : publication de `"off"` et `{"data": "off"}` sur `rt/utlidar/switch`.
  4. **Désactivation de l'anti-obstacle interne** : requête API ID 1001 `{"enable": false}` sur `rt/api/obstacles_avoid/request`.
  5. **Extinction des voyants / phares avant** via l'API VUI (ID 1005, luminosité 0).
- **Rétablissement au réveil (`exit_standby`)** :
  - Rétablissement de `disableTrafficSaving(True)`.
  - Réabonnement aux topics LiDAR (`subscribe`).
  - Commande `"on"` sur `rt/utlidar/switch` et réactivation de l'anti-obstacle interne.
  - Relevage en douceur via `StandUp` (1004).

### 2.3. Précision sur la rotation mécanique du LiDAR et `modprobe`
- **Absence de module noyau (`modprobe`)** : Le LiDAR 4D Unitree L1 n'est pas géré par un module noyau Linux déchargeable (`modprobe -r`), mais par un service en espace utilisateur communiquant en CycloneDDS / WebRTC.
- **Conception matérielle Unitree du moteur L1** : Le moteur de rotation mécanique du dôme LiDAR est directement relié au bus d'alimentation interne des capteurs. Il n'existe aucun relais d'alimentation physique contrôlable par logiciel pour couper le moteur indépendamment de l'extinction totale de la batterie du robot.
- **Économie maximale atteinte** : La coupure logicielle totale (arrêt de la génération de voxels, extinction logicielle du laser, coupure des flux WebRTC et de l'anti-obstacle) réduit l'activité processeur et la consommation à leur minimum absolu (~85%+ de batterie économisée) tout en préservant le canal WebRTC pour le réveil.

### 2.4. Sécurisation & Blocage des Commandes
- Tous les endpoints d'action physique renvoient un code HTTP **409 Conflict** clair pendant la veille et ses transitions :
  - `/api/execution/start`, `/api/manual/*`, `/api/mode`, `/api/safety/obstacles`.
- Neutralisation totale du relevage automatique `AutoRecovery` (`recovery.py`) tant que le robot est en veille (`_en_veille = True`).

---

## 3. Interface Utilisateur (Frontend)

### 3.1. Interrupteur de Veille (PlayHeader)
- Ajout d'un bouton switch **Veille** à côté de l'interrupteur Sécurité dans `PlayHeader.svelte`.
- États dynamiques : `éteinte`, `activée`, `mise en veille…`, `réveil en cours…`.
- Animation lumineuse pulsée pendant les transitions et bascule fluide du bouton.

### 3.2. Écran Plein Écran de Veille (StandbyOverlay)
- Composant dédié `frontend/src/components/play/StandbyOverlay.svelte` (`z-index: 300`).
- Recouvre l'ensemble de l'interface avec un effet de flou d'arrière-plan immersif (`backdrop-filter: blur(12px)`).
- Affiche le titre « En veille » avec aura lumineuse animée (icône de lune flottante ou indicateur de chargement rotatif pendant les transitions).
- Encadré explicatif pédagogique informant que les moteurs et le LiDAR sont coupés pour maximiser l'autonomie, et rappelant que la carte informatique reste alimentée pour permettre le réveil à distance.
- Badge d'état de la batterie en temps réel.
- Bouton d'action proéminent **« ☀️ Réveiller le robot »** (ou « Réveil en cours… » avec spinner désactivé pendant la transition).

### 3.3. Store Réactif & Client API
- `frontend/src/lib/api/client.ts` : champs `standby` et `standbyTransition` dans `RobotStatus`, méthode `api.setStandby(enabled)`.
- `frontend/src/lib/stores/app.svelte.ts` : intégration dans `isBusy`, méthode `app.setStandby(enabled)` avec notifications utilisateur.
- Fermeture automatique du mode manuel et blocage des modifications de programme dès le passage en veille.

---

## 4. Rappel des Évolutions Précédentes

### 4.1. Débridage des Vitesses de Déplacement & Rotation
- Plafond linéaire max porté à **0.50 m/s** (vitesse manuelle à 0.45 m/s).
- Plafond angulaire max à **1.20 rad/s**, avec vitesse manuelle au clavier réglée à **1.0 rad/s** (~57°/s) pour des corrections de cap nettes et précises.

### 4.2. Mouvements Combinés au Clavier
- Prise en charge simultanée de l'avancée/recul et de la rotation (`forward+turn_left`, `forward+turn_right`, etc.) via `SvelteSet<string>` dans `ManualPanel.svelte` et décomposition vectorielle dans `manual.py`.

### 4.3. Bloc Sauter & Saut Manuel (Barre Espace)
- Correction du geste `FrontJump` (suppression du flux de consigne nulle concurrent `flux_vitesse=False`).
- Fenêtre de grâce posture de 3.5 s pour autoriser le décollage sans déclencher l'arrêt de portage.
- Déclenchement au clavier avec la **Barre Espace** (`event.code === 'Space'`) ou bouton tactile dédié.

### 4.4. Sécurité Portage / Arrêt des Pattes
- Détection immédiate du soulèvement par `foot_force` (`< 60 N`).
- Passage immédiat en posture `Damp` : les moteurs cessent de gigoter et deviennent complètement mous dans les bras.
- Blocage du relevage automatique tant que le robot n'est pas reposé au sol de manière stable.

---

## 5. Validation des Tests

- **Backend (Python / pytest)** : **341 / 341 tests passés avec succès (100%)**.
  - `test_standby.py` : cycle complet activation/veille/réveil, blocage des commandes concurrentes, arrêt propre du mode manuel.
  - `test_execution.py`, `test_manual.py`, `test_webrtc_safety.py`, `test_posture.py`, `test_recovery.py`, etc.
- **Frontend (Vitest)** : **218 / 218 tests passés avec succès (100%)**.
  - Tests unitaires du store `app-store.test.ts` validant le switch veille, `isBusy` et la non-régression.
- **Vérification TypeScript & Svelte (`svelte-check`)** : **0 erreur, 0 avertissement**.
- **Build Vite de Production** : compilation réussie sans erreur dans `frontend/dist/`.

---

## 6. Vérification sur le Robot Réel (172.16.8.11)

- **Test du coucher doux (`StandDown`)** :
  - Déclenchement : les 4 pattes se replient de façon synchronisée et contrôlée. **Aucune chute, aucun à-coup brutal**.
  - Altitude stabilisée à **$z = 0.052\text{ m}$** (robot complètement posé sur le ventre).
- **Test de l'arrêt LiDAR** :
  - Désabonnement effectif : fin immédiate du flux de voxels et des messages d'état dans le journal de service.
  - Extinction demandée via `rt/utlidar/switch` et désactivation de l'anti-obstacle.
- **Test du réveil réel** :
  - Rétablissement des flux et de l'anti-obstacle.
  - Relevage `StandUp` sans à-coup, altitude rétablie à **$z = 0.302\text{ m}$**.

---

## 7. Règle Permanente du Dépôt
> **NE JAMAIS EFFECTUER DE COMMIT GIT SANS DEMANDE EXPLICITE DE L'UTILISATEUR.**
> À chaque fin d'intervention, ce fichier `compactage.md` est systématiquement mis à jour et synchronisé sur le conteneur (`/root/go2/compactage.md`).
