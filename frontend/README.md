# GO2 Scratch — interface (frontend)

Interface d'édition de programmes pour enfants, en Svelte + TypeScript + Blockly.

**La documentation du projet se trouve à la racine du dépôt :**
voir [`../README.md`](../README.md) et le dossier [`../docs/`](../docs/).

## Démarrage rapide

```cmd
npm install
npm run dev
```

Puis <http://localhost:5173>.

Le service robot doit tourner séparément (voir `../docs/INSTALLATION.md`).
Sans lui, l'application démarre en simulation mais affiche « Robot non
connecté ».

## Commandes

| Commande | Rôle |
|---|---|
| `npm run dev` | serveur de développement |
| `npm run build` | build de production dans `dist/` |
| `npm run preview` | prévisualiser le build |
| `npm run check` | vérification des types (svelte-check + tsc) |
| `npm test` | tests unitaires (Vitest) |

## Organisation

```
src/
├─ App.svelte              assemblage des 4 zones
├─ components/             barre, éditeur, contrôle, missions, aide, mode
├─ lib/
│  ├─ blockly/             blocs, palette, compilation vers instructions
│  ├─ robot/               modèle de commandes, limites, mouvement, validation
│  ├─ programs/            stockage local des missions
│  ├─ api/                 client HTTP / WebSocket
│  └─ stores/              état applicatif
└─ styles/app.css          identité visuelle
tests/                     tests unitaires
```

## Points importants

- **Aucun accès direct au robot.** Tout passe par `lib/api/client.ts`.
- **Aucun `eval`, aucun `Function()`.** Le compilateur produit une structure de
  données, pas du code.
- **Les limites de sécurité** viennent de `../shared/safety-limits.json`, lu
  aussi par le service. Ne pas dupliquer ces valeurs ici.
- **Les textes de l'interface sont en français** ; le code est en anglais.

### Réglages et siapa plafond

`lib/robot/settings.ts` décrit les réglages pour l'affichage (libellé, unité,
aide, pas de curseur). Il ne calcule **aucune borne** : celles-ci viennent de
`GET /api/settings`. C'est volontaire — si le frontend calculait les plafonds,
un client modifié pourrait les élargir.

Le service (`config.HARD_CEILINGS`) est seul à pouvoir les fixer.

### Contrats HTTP : pièges connus

Le service utilise des modèles Pydantic en `extra="forbid"`. Conséquence :
**toute divergence de casse sur un nom de champ est un 422, pas un silence.**

| Route | Champ attendu |
|---|---|
| `POST /api/execution/start` | `adult_authorised` |
| `POST /api/mode` | `adult_authorised` |
| `POST /api/settings` | `adult_authorised` |
| `POST /api/execution/heartbeat` | `run_id` |

Deux bugs de ce type ont déjà été rencontrés et coûté une session
(`runId`/`run_id`, `adultAuthorised`/`adult_authorised`). Le premier a fait
déclencher l'arrêt de sécurité à tort. **Tout nouveau contrat doit être
verrouillé par un test de forme de payload côté service.**