/**
 * Définition des blocs GO2 Scratch (français), pour enfants de 10 ans.
 *
 * ## Règle n°1 : aucun trou vide
 *
 * Toutes les valeurs se choisissent dans un MENU (`FieldDropdown`), jamais
 * dans un emplacement à remplir. Une entrée de valeur (`appendValueInput`)
 * dessine un creux visible tant que rien n'y est branché : c'est exactement
 * ce qui rendait l'ancien espace de travail troué, avec des blocs
 * « Avancer à la vitesse [ ] pendant [ ] » et deux encoches décoratives.
 *
 * Il n'existe donc **aucun** bloc à sortie dans cette application. Conséquence
 * assumée : pas de trous, pas de formes d'encoche à faire coïncider, et
 * aucune possibilité d'assembler deux blocs de façon incorrecte — il n'y a
 * plus rien à assembler.
 *
 * ## Règle n°2 : des blocs qui disent ce qu'ils font
 *
 * - Un bloc s'enchaîne en haut et en bas : `previous` + `next`.
 * - « Arrêter le programme » est terminal : `previous` seul, **pas** de
 *   `next`. Une encoche basse sous un bloc qui termine la chaîne est un
 *   mensonge : elle promet une suite possible.
 * - « Quand je clique sur Démarrer » est un bloc de départ : `next` seul.
 * - « Répéter », « Si » et « Si … sinon » portent des corps (`DO`, `ELSE`).
 *
 * ## Règle n°3 : pas de variables
 *
 * Un enfant de 10 ans ne crée pas de variable. Toutes les valeurs sont des
 * choix, pas des noms à inventer.
 *
 * ## Ce que le robot permet RÉELLEMENT
 *
 * `SportClient.Move(vx, vy, vyaw)` prend une VITESSE, jamais une distance.
 * Avancer « de 50 cm » n'existe donc pas dans le SDK. Deux conséquences :
 *
 * - Les déplacements linaires sont exprimés en DURÉE (« Avancer pendant 2
 *   secondes »). C'est ce que le robot sait faire, et ce qu'il fait bien.
 * - Les rotations, elles, sont exprimées en DEGRÉS : le cap (`yaw`) est une
 *   donnée MESURÉE de `SportModeState_`. « Tourner de 90° » est donc
 *   mesurable, et le service s'arrête quand le cap est atteint. C'est
 *   vérifiable, contrairement à une distance.
 *
 * La vitesse est choisie par le service, pas par l'enfant : moins de
 * paramètres, moins d'erreurs, et la limite de sécurité ne peut pas être
 * dépassée par une saisie.
 */

import * as Blockly from 'blockly/core';
import { SAFETY } from '../robot/limits';
import { applyFrenchLocale } from './locale';

// --------------------------------------------------------------------------
// Catégories
// --------------------------------------------------------------------------

export const CATEGORY_COLOURS = {
  movement: '#3D7BFE',
  actions: '#8E53D8',
  control: '#F2A33C',
} as const;

export type CategoryName = keyof typeof CATEGORY_COLOURS;

export const CATEGORIES: ReadonlyArray<{ name: CategoryName; label: string }> = [
  { name: 'movement', label: 'Déplacements' },
  { name: 'actions', label: 'Actions' },
  { name: 'control', label: 'Contrôle' },
];

// --------------------------------------------------------------------------
// Types de blocs
// --------------------------------------------------------------------------

export const START_BLOCK = 'go2_start';
export const MOVE_FORWARD_BLOCK = 'go2_move_forward';
export const MOVE_BACKWARD_BLOCK = 'go2_move_backward';
export const MOVE_LEFT_BLOCK = 'go2_move_left';
export const MOVE_RIGHT_BLOCK = 'go2_move_right';
export const TURN_LEFT_BLOCK = 'go2_turn_left';
export const TURN_RIGHT_BLOCK = 'go2_turn_right';
export const STOP_MOVE_BLOCK = 'go2_stop_move';
export const STAND_UP_BLOCK = 'go2_stand_up';
export const SIT_DOWN_BLOCK = 'go2_sit_down';
export const BALANCE_BLOCK = 'go2_balance';
export const WAIT_BLOCK = 'go2_wait';
export const REPEAT_BLOCK = 'go2_repeat';
export const IF_BLOCK = 'go2_if';
export const IF_ELSE_BLOCK = 'go2_if_else';
export const STOP_PROGRAM_BLOCK = 'go2_stop_program';

// --------------------------------------------------------------------------
// Choix proposés aux enfants
// --------------------------------------------------------------------------

/**
 * Durées proposées.
 *
 * Volontairement courtes et en nombres ronds : c'est ce qu'un enfant peut
 * concevoir sans calculatrice. La borne reste celle du service
 * (`max_wait_seconds`), et le service revérifie.
 */
export const DURATION_CHOICES: ReadonlyArray<[string, string]> = [
  ['1 seconde', '1'],
  ['2 secondes', '2'],
  ['3 secondes', '3'],
  ['5 secondes', '5'],
];

export const TURN_CHOICES: ReadonlyArray<[string, string]> = [
  ['45°', '45'],
  ['90°', '90'],
  ['180°', '180'],
];

/**
 * Nombres de répétitions proposés.
 *
 * ⚠️ Les libellés sont des NOMBRES, pas « 2 fois ».
 *
 * Blockly 13 remplace le libellé d'une option par sa valeur lorsque le
 * libellé est purement numérique : une option `['2 fois', '2']` s'affiche
 * « 2 » dans le menu. Le mot « fois » est donc porté par un libellé du BLOC,
 * ce qui donne « Répéter [3 ▾] fois » à l'écran et « 2 / 3 / 5 / 10 » dans le
 * menu : les deux se complètent au lieu de se contredire.
 */
export const REPEAT_CHOICES: ReadonlyArray<[string, string]> = [
  ['2', '2'],
  ['3', '3'],
  ['5', '5'],
  ['10', '10'],
];

/**
 * Conditions proposées.
 *
 * ⚠️ Chaque entrée doit être RÉELLEMENT implémentée et mesurable. Il n'y a
 * volontairement pas de « si un obstacle est détecté » : aucune mesure de
 * distance n'a été identifiée dans le SDK officiel lu. Proposer ce bloc
 * reviendrait à afficher une valeur inventée.
 *
 * - « le robot est debout » : posture tenue par le service.
 * - « la batterie est faible » : `SportModeState_.bms` / batterie, lue.
 */
export const CONDITION_CHOICES: ReadonlyArray<[string, string]> = [
  ['le robot est debout', 'posture_stand'],
  ['la batterie est faible', 'battery_low'],
];

//: En dessous de ce pourcentage, la batterie est considérée faible.
//  La valeur vit dans `robot/bounds` : la validation enfant l'importe sans
//  embarquer Blockly.
export { LOW_BATTERY_PERCENT } from '../robot/bounds';

// --------------------------------------------------------------------------
// Métadonnées
// --------------------------------------------------------------------------

export interface BlockDefinition {
  type: string;
  category: CategoryName;
  /** Libellé complet attendu, vérifié par `verifyBlockLabels()`. */
  label: string;
  /**
   * Commandes du service réellement mobilisées. Vide pour les blocs purely
   * structurels (boucles, conditions).
   */
  commands: readonly string[];
  /**
   * `false` si l'action n'est PAS confirmée dans le SDK lu. Le bloc reste
   * utilisable en simulation, mais le service refuse de l'exécuter en mode
   * réel : ce qui n'a pas été vérifié ne passe pas en pilotage.
   */
  verifiedForRealMode: boolean;
}

export const BLOCK_DEFINITIONS: readonly BlockDefinition[] = [
  {
    type: MOVE_FORWARD_BLOCK,
    category: 'movement',
    label: 'Avancer pendant',
    commands: ['move'],
    verifiedForRealMode: true,
  },
  {
    type: MOVE_BACKWARD_BLOCK,
    category: 'movement',
    label: 'Reculer pendant',
    commands: ['move'],
    verifiedForRealMode: true,
  },
  {
    type: MOVE_LEFT_BLOCK,
    category: 'movement',
    label: 'Aller à gauche pendant',
    commands: ['move'],
    verifiedForRealMode: true,
  },
  {
    type: MOVE_RIGHT_BLOCK,
    category: 'movement',
    label: 'Aller à droite pendant',
    commands: ['move'],
    verifiedForRealMode: true,
  },
  {
    type: TURN_LEFT_BLOCK,
    category: 'movement',
    label: 'Tourner à gauche de',
    commands: ['turn'],
    verifiedForRealMode: true,
  },
  {
    type: TURN_RIGHT_BLOCK,
    category: 'movement',
    label: 'Tourner à droite de',
    commands: ['turn'],
    verifiedForRealMode: true,
  },
  {
    type: STOP_MOVE_BLOCK,
    category: 'movement',
    label: 'Arrêter le robot',
    commands: ['stop'],
    verifiedForRealMode: true,
  },
  {
    type: STAND_UP_BLOCK,
    category: 'actions',
    label: 'Se mettre debout',
    commands: ['stand_up'],
    verifiedForRealMode: true,
  },
  {
    type: SIT_DOWN_BLOCK,
    category: 'actions',
    label: "S'asseoir",
    commands: ['sit_down'],
    verifiedForRealMode: true,
  },
  {
    type: BALANCE_BLOCK,
    category: 'actions',
    label: 'Se stabiliser',
    commands: ['balance'],
    verifiedForRealMode: true,
  },
  {
    type: START_BLOCK,
    category: 'control',
    label: 'Quand je clique sur Démarrer',
    commands: [],
    verifiedForRealMode: true,
  },
  {
    type: WAIT_BLOCK,
    category: 'control',
    label: 'Attendre',
    commands: ['wait'],
    verifiedForRealMode: true,
  },
  {
    type: REPEAT_BLOCK,
    category: 'control',
    label: 'Répéter',
    commands: [],
    verifiedForRealMode: true,
  },
  {
    type: IF_BLOCK,
    category: 'control',
    label: 'Si',
    commands: [],
    verifiedForRealMode: true,
  },
  {
    type: IF_ELSE_BLOCK,
    category: 'control',
    label: 'Si',
    commands: [],
    verifiedForRealMode: true,
  },
  {
    type: STOP_PROGRAM_BLOCK,
    category: 'control',
    label: 'Arrêter le programme',
    commands: ['stop_program'],
    verifiedForRealMode: true,
  },
];

// --------------------------------------------------------------------------
// Helpers de construction
// --------------------------------------------------------------------------

/**
 * Construit un menu déroulant.
 *
 * ⚠️ `FieldDropdown` n'a PAS de `setName()`. Et `appendField(field)` sans nom
 * laisse `field.name === undefined` : le champ est affiché mais pas
 * enregistré, donc `getFieldValue()` renvoie `null` et le compilateur conclut
 * qu'il manque une valeur. Le nom est donc passé à `appendField`.
 *
 * On renvoie le CHAMP, pas l'entrée : l'en-tête doit regrouper texte, menu et
 * unité dans UNE seule entrée factice. Avec une entrée par champ et
 * `setInputsInline(false)` — nécessaire pour que le corps passe sur sa propre
 * ligne —, Blockly place chaque entrée sur SA LIGNE : « Répéter » / « 3 » /
 * « fois » empilés verticalement, illisibles.
 */
function menu(
  choices: ReadonlyArray<[string, string]>,
  defaultValue: string,
): Blockly.FieldDropdown {
  const field = new Blockly.FieldDropdown(choices.map(([label, value]) => [label, value]));
  field.setValue(defaultValue);
  return field;
}

/** Bloc simple : s'enchaîne au-dessus et en dessous. */
function chainBlock(block: Blockly.Block, text: string, colour: string): void {
  block.appendDummyInput('HEAD').appendField(text);
  block.setPreviousStatement(true);
  block.setNextStatement(true);
  block.setColour(colour);
}

/** Bloc de déplacement : un en-tête sur une seule ligne. */
function durationBlock(
  block: Blockly.Block,
  leadingText: string,
  colour: string,
  defaultSeconds = '2',
): void {
  block
    .appendDummyInput('HEAD')
    .appendField(leadingText)
    .appendField(menu(DURATION_CHOICES, defaultSeconds), 'DURATION');
  block.setPreviousStatement(true);
  block.setNextStatement(true);
  block.setColour(colour);
}

/** Bloc de rotation : un en-tête sur une seule ligne. */
function turnBlock(block: Blockly.Block, leadingText: string, colour: string): void {
  block
    .appendDummyInput('HEAD')
    .appendField(leadingText)
    .appendField(menu(TURN_CHOICES, '90'), 'ANGLE');
  block.setPreviousStatement(true);
  block.setNextStatement(true);
  block.setColour(colour);
}

/**
 * Bloc conditionnel.
 *
 * La condition est un MENU, pas une encoche à remplir : un enfant n'a rien à
 * brancher, et il ne peut donc pas laisser un trou.
 */
function ifBlock(
  block: Blockly.Block,
  colour: string,
  withElse: boolean,
): void {
  // « Si … alors » sur UNE ligne, puis le corps en dessous.
  block
    .appendDummyInput('HEAD')
    .appendField('Si')
    .appendField(menu(CONDITION_CHOICES, 'posture_stand'), 'CONDITION')
    .appendField('alors');
  block.appendStatementInput('DO');
  if (withElse) {
    block.appendDummyInput('ELSE_HEAD').appendField('sinon');
    block.appendStatementInput('ELSE');
  }
  // `false` : le corps doit passer sur sa propre ligne. Les en-têtes sont
  // déjà regroupés en une entrée chacun, donc rien ne se disperse.
  block.setInputsInline(false);
  block.setPreviousStatement(true);
  block.setNextStatement(true);
  block.setColour(colour);
}

/**
 * Enregistre tous les blocs GO2 sur le namespace Blockly. Idempotent.
 *
 * La locale française est appliquée ici, et non laissée à l'appelant :
 * `FieldDropdown` construit ses options à partir de messages localisés, et
 * appelle `.replace()` dessus. Sans locale, ce message vaut `undefined` et la
 * création du bloc **échoue**.
 */
export function registerGo2Blocks(): void {
  applyFrenchLocale();

  if (Blockly.Blocks[START_BLOCK] !== undefined) return;

  // --- Déplacements -------------------------------------------------------

  Blockly.Blocks[MOVE_FORWARD_BLOCK] = {
    init(this: Blockly.Block) {
      durationBlock(this, 'Avancer pendant', CATEGORY_COLOURS.movement);
      this.setTooltip('Le robot avance tout droit pendant ce temps.');
    },
  };

  Blockly.Blocks[MOVE_BACKWARD_BLOCK] = {
    init(this: Blockly.Block) {
      durationBlock(this, 'Reculer pendant', CATEGORY_COLOURS.movement);
      this.setTooltip('Le robot recule tout droit pendant ce temps.');
    },
  };

  Blockly.Blocks[MOVE_LEFT_BLOCK] = {
    init(this: Blockly.Block) {
      durationBlock(this, 'Aller à gauche pendant', CATEGORY_COLOURS.movement);
      this.setTooltip('Le robot glisse vers la gauche pendant ce temps.');
    },
  };

  Blockly.Blocks[MOVE_RIGHT_BLOCK] = {
    init(this: Blockly.Block) {
      durationBlock(this, 'Aller à droite pendant', CATEGORY_COLOURS.movement);
      this.setTooltip('Le robot glisse vers la droite pendant ce temps.');
    },
  };

  Blockly.Blocks[TURN_LEFT_BLOCK] = {
    init(this: Blockly.Block) {
      turnBlock(this, 'Tourner à gauche de', CATEGORY_COLOURS.movement);
      this.setTooltip('Le robot tourne sur lui-même jusqu’à l’angle choisi.');
    },
  };

  Blockly.Blocks[TURN_RIGHT_BLOCK] = {
    init(this: Blockly.Block) {
      turnBlock(this, 'Tourner à droite de', CATEGORY_COLOURS.movement);
      this.setTooltip('Le robot tourne sur lui-même jusqu’à l’angle choisi.');
    },
  };

  Blockly.Blocks[STOP_MOVE_BLOCK] = {
    init(this: Blockly.Block) {
      chainBlock(this, 'Arrêter le robot', CATEGORY_COLOURS.movement);
      this.setTooltip('Le robot s’immobilise tout de suite.');
    },
  };

  // --- Actions ------------------------------------------------------------

  Blockly.Blocks[STAND_UP_BLOCK] = {
    init(this: Blockly.Block) {
      chainBlock(this, 'Se mettre debout', CATEGORY_COLOURS.actions);
    },
  };

  Blockly.Blocks[SIT_DOWN_BLOCK] = {
    init(this: Blockly.Block) {
      chainBlock(this, "S'asseoir", CATEGORY_COLOURS.actions);
    },
  };

  Blockly.Blocks[BALANCE_BLOCK] = {
    init(this: Blockly.Block) {
      chainBlock(this, 'Se stabiliser', CATEGORY_COLOURS.actions);
      this.setTooltip('Le robot se tient bien droit sur ses quatre pattes.');
    },
  };

  // --- Contrôle -----------------------------------------------------------

  Blockly.Blocks[START_BLOCK] = {
    init(this: Blockly.Block) {
      // Bloc de départ : une encoche en bas, AUCUNE en haut.
      this.appendDummyInput('HEAD').appendField('Quand je clique sur Démarrer');
      this.setStyle('hat_blocks');
      this.setNextStatement(true);
      this.setColour(CATEGORY_COLOURS.control);
      this.setTooltip('Accroche tes blocs ici.');
    },
  };

  Blockly.Blocks[WAIT_BLOCK] = {
    init(this: Blockly.Block) {
      this.appendDummyInput('HEAD')
        .appendField('Attendre')
        .appendField(menu(DURATION_CHOICES, '2'), 'SECONDS');
      this.setPreviousStatement(true);
      this.setNextStatement(true);
      this.setColour(CATEGORY_COLOURS.control);
      this.setTooltip('Le robot ne bouge pas pendant ce temps.');
    },
  };

  Blockly.Blocks[REPEAT_BLOCK] = {
    init(this: Blockly.Block) {
      // Une seule entrée d'en-tête : sinon « Répéter », le menu et « fois »
      // tombent sur trois lignes distinctes.
      this.appendDummyInput('HEAD')
        .appendField('Répéter')
        .appendField(menu(REPEAT_CHOICES, '3'), 'COUNT')
        .appendField('fois');
      this.appendStatementInput('DO');
      this.setInputsInline(false);
      this.setPreviousStatement(true);
      this.setNextStatement(true);
      this.setColour(CATEGORY_COLOURS.control);
      this.setTooltip('Le bloc répété fait ce qu’il y a écrit en dessous.');
    },
  };

  Blockly.Blocks[IF_BLOCK] = {
    init(this: Blockly.Block) {
      ifBlock(this, CATEGORY_COLOURS.control, false);
    },
  };

  Blockly.Blocks[IF_ELSE_BLOCK] = {
    init(this: Blockly.Block) {
      ifBlock(this, CATEGORY_COLOURS.control, true);
    },
  };

  Blockly.Blocks[STOP_PROGRAM_BLOCK] = {
    init(this: Blockly.Block) {
      // Bloc TERMINAL : encoche en haut, PAS d'encoche en bas. Une encoche
      // basse prometrait une suite possible après « Arrêter le programme ».
      this.appendDummyInput('HEAD').appendField('Arrêter le programme');
      this.setPreviousStatement(true);
      this.setColour(CATEGORY_COLOURS.control);
      this.setTooltip('Le programme s’arrête ici, même s’il reste des blocs.');
    },
  };
}

/**
 * Contrôle que tous les blocs déclarés portent un libellé.
 *
 * Utilisé par les tests : garantit qu'aucun bloc ne peut être livré muet.
 */
export function verifyBlockLabels(): Array<{ type: string; problem: string }> {
  const problems: Array<{ type: string; problem: string }> = [];
  for (const definition of BLOCK_DEFINITIONS) {
    if (definition.label.trim().length === 0) {
      problems.push({ type: definition.type, problem: 'libellé déclaré vide' });
    }
  }
  return problems;
}

/** Types de blocs acceptés par le compilateur. */
export const COMPILABLE_BLOCKS: ReadonlySet<string> = new Set(
  BLOCK_DEFINITIONS.map((definition) => definition.type),
);

/** Postures exposées, telles que le service les connaît. */
export const POSTURES = ['stand', 'sit', 'balance'] as const;

/** Conditions réellement implémentées. */
export const CONDITIONS = ['posture_stand', 'battery_low'] as const;

/** Borne de durée partagée avec la validation (voir `robot/bounds`). */
export { MAX_DURATION_S } from '../robot/bounds';