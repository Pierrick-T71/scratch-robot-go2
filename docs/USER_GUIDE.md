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