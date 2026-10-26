# USER GUIDE — Guide d'utilisation

Deux parties : un guide pour les **animateurs** et un guide pour les **enfants**.

---

# Partie 1 — Pour les animateurs

## Avant la session

1. Lancer le service (terminal 1) et l'interface (terminal 2).
2. Vérifier que l'écran affiche **Mode simulation** et **Robot connecté**.
3. **Commencer toujours en simulation.**
4. Si le robot réel est utilisé, lire `docs/SAFETY.md` et vérifier la zone.

## Avant la séance : régler le robot

Le panneau **⚙️ Configuration** permet d'adapter les limites à l'âge des enfants
et à la taille de la salle. C'est le premier réflexe avant une séance réelle.

Par exemple, avec des enfants de 10 ans dans une petite salle, on peut juger
raisonnable de régler :

| Réglage | Valeur | Pourquoi |
|---|---|---|
| Vitesse maximale | 0,15 m/s | marche lente |
| Distance par déplacement | 80 cm | pas de traversée de la salle |
| Durée totale | 60 s | pas de programme qui s'éternise |

Ces valeurs restent **sous** les plafonds du code : on ne peut pas accélérer le
robot au-delà de ce qui a été livré et validé.

Après un changement, **faire vérifier les missions déjà écrites** : elles ont pu
devenir invalides.

## Règles d'or

- Un adulte **regarde le robot**, pas l'écran.
- La télécommande est **en main**.
- Le bouton rouge **Arrêter** est toujours visible.
- On arrête immédiatement si le robot fait quelque chose d'inattendu.
- Le logiciel ne remplace jamais l'arrêt d'urgence physique.

## Déroulé d'une séance type

1. **Découvrir** (10 min) — en simulation : déplacer des blocs, « Vérifier ».
2. **Exécuter** (15 min) — lancer des missions simples, regarder la progression.
3. **Créer** (15 min) — chaque enfant invente une mission et lui donne un nom.
4. **Sur le robot** (si prêt) — une mission chacun, très court, avec surveillance.

---

# Partie 2 — Pour les enfants

## Les 4 étapes

### 1. Je compose

- Les blocs sont **à gauche**.
- Prends un bloc et **accroche-le sous le bloc orange** « Quand je clique sur
  Démarrer ».
- Clique sur un nombre pour le changer.

### 2. Je vérifie

Clique sur **🔍 Vérifier mon programme**.

- ✅ **« Bravo ! Ton programme est prêt. »** → tu peux démarrer.
- ⛔ Sinon, un message t'explique quoi corriger.

### 3. Je démarre

Clique sur **▶️ Démarrer**. La liste de droite montre les étapes une par une.

### 4. J'arrête si besoin

Clique sur **⛔ Arrêter**.

Si le robot bouge encore, **préviens l'adulte tout de suite**.

### 5. Si un mur est trop près

Le robot regarde devant lui avec son **lidar**. S'il n'y a pas assez de place
pour faire **toute** l'action, il ne la fait pas :

- l'étape devient **orange** avec « Pas assez de place devant » ;
- le programme **continue** avec les autres étapes ;
- il ne raccourcit pas l'action : il préfère ne rien faire plutôt que de foncer
  dans le mur.

Un mur à 1 m laisse passer un pas de **1 seconde**, mais pas un pas de
**5 secondes** : en 5 secondes, le chien parcourt 1,50 m et toucherait le mur.

Si quelqu'un passe devant lui **pendant** un déplacement, il s'arrête.

Quand une action est refusée, une **fenêtre au milieu de l'écran** affiche le
message complet (par exemple « Pas assez de place devant : il reste 0,8 m
libres »). Clique sur **Fermer** après avoir lu. Si tu ne comprends pas,
**demande à l'adulte**.

Il ne voit pas les **vitres**, ni les objets **très bas** (moins de 25 cm) :
l'adulte regarde toujours le robot.

### 6. Si le robot est soulevé

Le robot s'arrête **tout seul** et relâche ses pattes. Un bandeau rouge
s'affiche.

- Pose-le **doucement au sol**.
- Attends **une seconde** sans le tenir.
- S'il reste allongé et que le bandeau reste affiché, **demande à l'adulte**.

Ne le relance pas pendant que tu le tiens.

### 7. Si le robot s'est allongé tout seul

Si le robot s'est allongé **et** que son lidar (le petit capteur devant sa
tête) est coincé contre le sol, il **se relève tout seul**. Un bandeau vert
te le dit.

S'il n'y arrive pas, **demande à l'adulte** : il faut le redresser à la
main.

### 8. Voir le robot

La petite fenêtre montre le robot **de dos**, comme si tu étais juste
derrière lui : ce qui est devant lui est au fond de l'image, et le chien ne
cache pas la suite du chemin.

- Le bouton **radar** (en haut à gauche) affiche les obstacles vus par le
  lidar. Ils arrivent **devant** le chien, là où ils sont vraiment.
- Le bouton **caméra** (en haut à droite) montre ce que voit la caméra du
  robot.
- Appuie une deuxième fois sur le même bouton pour revenir au robot 3D.

---

## Les blocs

### 🟠 Quand ça commence

| Bloc | Ce qu'il fait |
|---|---|
| Quand je clique sur Démarrer | Le début de ton programme |

### 🔵 Déplacements

| Bloc | Ce qu'il fait |
|---|---|
| Avancer de … cm | Le robot avance tout droit |
| Reculer de … cm | Le robot recule |
| Tourner à gauche de … degrés | Le robot tourne sur lui-même |
| Tourner à droite de … degrés | Le robot tourne dans l'autre sens |
| S'arrêter | Le robot s'arrête |

### 🟢 Actions

| Bloc | Ce qu'il fait |
|---|---|
| Se mettre debout | Le robot se lève |
| S'asseoir | Le robot se rassoit |

### 🟣 Contrôle

| Bloc | Ce qu'il fait |
|---|---|
| Répéter … fois | Refait plusieurs fois ce qui est à l'intérieur |

---

## Les 3 missions pour commencer

### Modifier un nombre

Chaque bloc qui demande une quantité porte un **nombre** que tu peux changer :

| Bloc | Ce qui est modifiable |
|---|---|
| Avancer de **50** cm | la distance |
| Tourner à gauche de **90** degrés | l'angle |
| Attendre **2** secondes | la durée |
| Répéter **3** fois | le nombre de répétitions |

Clique sur le nombre, efface, tape la nouvelle valeur, valide avec **Entrée**.

Le nombre est **borné** : impossible d'écrire 500 cm pour un seul « Avancer »,
la limite autorisée est plus basse. Si ton programme est refusé, le message te
dit jusqu'où tu peux aller.

### Mission 1 — Le tour de table

```
Quand je clique sur Démarrer
  Se mettre debout
  Avancer de 50 cm
  Tourner à gauche de 90 degrés
  Avancer de 50 cm
  Tourner à droite de 90 degrés
  Avancer de 50 cm
  Tourner à droite de 90 degrés
  Avancer de 50 cm
```

*Tu as fait le tour d'une table !*

### Mission 2 — Le carré

```
Quand je clique sur Démarrer
  Se mettre debout
  Répéter 4 fois
    Avancer de 40 cm
    Tourner à gauche de 90 degrés
```

*Avec 4 répétitions, on n'écrit qu'une fois !*

### Mission 3 — Le petit salut

```
Quand je clique sur Démarrer
  Se mettre debout
  Attendre 1 seconde
  S'asseoir
  Attendre 1 seconde
  Se mettre debout
```

---

## Mes messages préférés

| Ce que tu vois | Ce que ça veut dire |
|---|---|
| ✅ **« Bravo ! Ton programme est prêt. »** | Tout est bon, tu peux démarrer |
| ⛔ **« Il manque le bloc de départ. »** | Remets le bloc orange « Quand je clique sur Démarrer » |
| ⛔ **« Un bloc est seul, pas attaché au programme. »** | Ce bloc n'est accroché à rien : supprime-le ou raccroche-le |
| ⛔ **« Un déplacement doit faire entre 5 et 200 cm. »** | Ton nombre est trop grand ou trop petit |
| ⛔ **« Le programme n’est pas prêt. »** | Clique d'abord sur « Vérifier mon programme » |
| ⚠️ **« Le programme a été arrêté. »** | Quelqu'un a appuyé sur Arrêter, ou la sécurité a bloqué |
| 🚧 **« Le robot ne peut pas avancer »** | Il n'y a pas assez de place : lis la fenêtre, puis clique sur **Fermer** |
| ⛔ **« Le robot n'est pas connecté. »** | Demande de l'aide à l'adulte |
| **« mesuré · 45 cm »** | Le robot a **vraiment** mesuré son déplacement |
| **« temps écoulé »** | Le robot n'a pas réussi à arriver : demande à l'adulte |

---

## Changer les réglages (pour les adultes)

Clique sur **⚙️ Configuration** en haut à droite.

Tu peux y régler ce que le robot a le droit de faire : sa vitesse maximale, la
distance d’un déplacement, la durée d’une attente, la longueur d’un programme…

**Trois choses à savoir :**

- Il faut écrire **RÉGLAGES** en majuscules pour valider. C’est fait exprès pour
  qu’un enfant ne modifie pas les réglages sans faire exprès.
- On ne peut pas dépasser les limites affichées sous chaque curseur.
- Les réglages ne peuvent pas être changés pendant que le robot bouge.

Si les réglages ont changé, clique à nouveau sur **🔍 Vérifier mon programme**
avant de relancer.

---

## L'interrupteur « Sécurité » (pour les adultes)

En haut à droite, à côté de « Go2 Connecté », un interrupteur **Sécurité**
affiche l'état de la vérification de place du service :

- **activée** (vert, par défaut) : le service refuse un pas qui ne tient pas
  dans l'espace libre vu par le lidar, et arrête le robot si un obstacle
  apparaît pendant le pas ;
- **désactivée** (rouge) : le service **ne vérifie plus** la distance ;
  l’interrupteur reste rouge.

Pour la couper, il faut confirmer dans une fenêtre « Désactiver la sécurité ? ».
L'interrupteur n'est disponible que si le **robot réel est connecté** et
qu'aucun programme ne tourne. Il revient automatiquement sur **activée** à
chaque nouveau branchement.

> ⚠️ L'interrupteur ne coupe **que** le contrôle lidar du service. Le bouton
> Arrêter, le bail de sécurité, le chien de garde, les limites de vitesse, la
> protection de portage et l'anti-obstacle interne du Go2 restent actifs. Il
> ne faut le désactiver que pour un diagnostic, dans une zone dégagée, avec la
> télécommande en main.

---

## Mes missions

En bas à droite :

1. Écris un **nom** pour ta mission.
2. Clique sur **💾 Enregistrer**.
3. Ta mission est gardée sur cet ordinateur.
4. Clique sur **Ouvrir** pour la rejouer ou la modifier.
5. Le 🗑️ supprime la mission (on te demande confirmation).

---

## Trois règles

1. **Attends le signal de l'adulte** avant de lancer sur le vrai robot.
2. **Ne mets jamais la main** dans les pattes du robot, même à l'arrêt.
3. **Clique sur Arrêter** si quelque chose ne va pas — n'attends pas.

---

## Les mots compliqués, expliqués

| Mot | Ce que ça veut dire |
|---|---|
| **Programme** | la suite d'actions que tu as créée |
| **Mission** | un programme auquel tu as donné un nom |
| **Vérifier** | demander à l'ordinateur si ton programme peut marcher |
| **Mesurer** | le robot dit lui-même ce qu'il a vraiment fait |
| **Simulation** | un faux robot à l'écran : aucun vrai mouvement |
| **Sécurité** | les règles qui empêchent le robot de faire n'importe quoi |