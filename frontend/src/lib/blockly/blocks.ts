/**
 * Definition des blocs GO2 Scratch (francais).
 *
 * Chaque bloc est defini statiquement, sans generation de code. Aucun bloc
 * n'utilise `eval`, `Function`, ni du code arbitraire : le moteur interprete
 * une structure de donnees (`RobotCommand`) produite par le compilateur.
 *
 * Convention de nommage interne (anglais) / libelle enfant (francais).
 */
import * as Blockly from 'blockly/core';
import { SAFETY } from '../robot/limits';

const CATEGORY_COLOURS = {
  events: '#F2A33C',
  movement: '#3D7BFE',
  actions: '#12A57A',
  control: '#8E53D8',
};

/** Nom du bloc de depart du programme. */
export const START_BLOCK = 'go2_start';
export const WAIT_BLOCK = 'go2_wait';
export const FORWARD_BLOCK = 'go2_move_forward';
export const BACKWARD_BLOCK = 'go2_move_backward';
export const TURN_LEFT_BLOCK = 'go2_turn_left';
export const TURN_RIGHT_BLOCK = 'go2_turn_right';
export const STOP_BLOCK = 'go2_stop';
export const STAND_UP_BLOCK = 'go2_stand_up';
export const SIT_DOWN_BLOCK = 'go2_sit_down';
export const REPEAT_BLOCK = 'go2_repeat';

export interface BlockDefinition {
  type: string;
  category: string;
  colour: string;
  /** Bloc de demarrage :hat / statement (avec bloc suivant) ou statement sans suivant. */
  kind: 'hat' | 'statement' | 'statementNoNext';
}

/** Registre des blocs autorises. Toute entree inconnue sera rejetee. */
export const BLOCK_DEFINITIONS: readonly BlockDefinition[] = [
  { type: START_BLOCK, category: 'events', colour: CATEGORY_COLOURS.events, kind: 'hat' },
  { type: WAIT_BLOCK, category: 'events', colour: CATEGORY_COLOURS.events, kind: 'statement' },
  { type: FORWARD_BLOCK, category: 'movement', colour: CATEGORY_COLOURS.movement, kind: 'statement' },
  { type: BACKWARD_BLOCK, category: 'movement', colour: CATEGORY_COLOURS.movement, kind: 'statement' },
  { type: TURN_LEFT_BLOCK, category: 'movement', colour: CATEGORY_COLOURS.movement, kind: 'statement' },
  { type: TURN_RIGHT_BLOCK, category: 'movement', colour: CATEGORY_COLOURS.movement, kind: 'statement' },
  { type: STOP_BLOCK, category: 'movement', colour: CATEGORY_COLOURS.movement, kind: 'statement' },
  { type: STAND_UP_BLOCK, category: 'actions', colour: CATEGORY_COLOURS.actions, kind: 'statement' },
  { type: SIT_DOWN_BLOCK, category: 'actions', colour: CATEGORY_COLOURS.actions, kind: 'statement' },
  { type: REPEAT_BLOCK, category: 'control', colour: CATEGORY_COLOURS.control, kind: 'statement' },
];

const KNOWN_BLOCKS = new Set(BLOCK_DEFINITIONS.map((d) => d.type));

export function isKnownBlockType(type: string): boolean {
  return KNOWN_BLOCKS.has(type);
}

export const CATEGORIES = [
  { name: 'events', label: 'Quand ça commence', colour: CATEGORY_COLOURS.events },
  { name: 'movement', label: 'Déplacements', colour: CATEGORY_COLOURS.movement },
  { name: 'actions', label: 'Actions', colour: CATEGORY_COLOURS.actions },
  { name: 'control', label: 'Contrôle', colour: CATEGORY_COLOURS.control },
];

/** Ombre `math_number` : donne une valeur par defaut saisie et modifiable. */
function numberShadow(value: number): Record<string, unknown> {
  return { type: 'math_number', inputs: { NUM: value } };
}

/**
 * Enregistre tous les blocs GO2 sur le namespace Blockly. Idempotent.
 *
 * Les parametres sont des blocs-valeurs (`input_value` type Number) afin de
 * permettre l'imbrication. Les bornes ne sont donc pas posees ici mais
 * centralisees dans `validate.ts`, seule source de verite.
 */
export function registerGo2Blocks(): void {
  if (Blockly.Blocks[START_BLOCK] !== undefined) return;

  const dist = SAFETY.motion;
  const time = SAFETY.timing;
  const prog = SAFETY.program;

  // --- Événements -----------------------------------------------------------
  Blockly.defineBlocksWithJsonArray([
    {
      type: START_BLOCK,
      // Bloc de départ : simple texte. Un `button` ne ferait qu'ajouter une
      // dépendance d'affichage pour rien.
      message0: 'Quand je clique sur Démarrer',
      colour: CATEGORY_COLOURS.events,
      nextStatement: null,
      hat: 'cap',
    },
    {
      type: WAIT_BLOCK,
      message0: 'Attendre %1 secondes',
      args0: [
        {
          type: 'input_value',
          name: 'DURATION',
          check: 'Number',
          shadow: numberShadow(2),
        },
      ],
      colour: CATEGORY_COLOURS.events,
      previousStatement: null,
      nextStatement: null,
    },
  ]);

  // --- Déplacements ---------------------------------------------------------
  Blockly.defineBlocksWithJsonArray([
    {
      type: FORWARD_BLOCK,
      message0: 'Avancer de %1 cm',
      args0: [
        {
          type: 'input_value',
          name: 'DISTANCE',
          check: 'Number',
          shadow: numberShadow(50),
        },
      ],
      colour: CATEGORY_COLOURS.movement,
      previousStatement: null,
      nextStatement: null,
    },
    {
      type: BACKWARD_BLOCK,
      message0: 'Reculer de %1 cm',
      args0: [
        {
          type: 'input_value',
          name: 'DISTANCE',
          check: 'Number',
          shadow: numberShadow(50),
        },
      ],
      colour: CATEGORY_COLOURS.movement,
      previousStatement: null,
      nextStatement: null,
    },
    {
      type: TURN_LEFT_BLOCK,
      message0: 'Tourner à gauche de %1 degrés',
      args0: [
        {
          type: 'input_value',
          name: 'ANGLE',
          check: 'Number',
          shadow: numberShadow(90),
        },
      ],
      colour: CATEGORY_COLOURS.movement,
      previousStatement: null,
      nextStatement: null,
    },
    {
      type: TURN_RIGHT_BLOCK,
      message0: 'Tourner à droite de %1 degrés',
      args0: [
        {
          type: 'input_value',
          name: 'ANGLE',
          check: 'Number',
          shadow: numberShadow(90),
        },
      ],
      colour: CATEGORY_COLOURS.movement,
      previousStatement: null,
      nextStatement: null,
    },
    {
      type: STOP_BLOCK,
      message0: "S'arrêter",
      colour: CATEGORY_COLOURS.movement,
      previousStatement: null,
      nextStatement: null,
    },
  ]);

  // --- Actions ---------------------------------------------------------------
  Blockly.defineBlocksWithJsonArray([
    {
      type: STAND_UP_BLOCK,
      message0: 'Se mettre debout',
      colour: CATEGORY_COLOURS.actions,
      previousStatement: null,
      nextStatement: null,
    },
    {
      type: SIT_DOWN_BLOCK,
      message0: "S'asseoir",
      colour: CATEGORY_COLOURS.actions,
      previousStatement: null,
      nextStatement: null,
    },
  ]);

  // --- Contrôle -------------------------------------------------------------
  Blockly.defineBlocksWithJsonArray([
    {
      type: REPEAT_BLOCK,
      message0: 'Répéter %1 fois',
      args0: [
        {
          type: 'input_value',
          name: 'COUNT',
          check: 'Number',
          shadow: numberShadow(3),
        },
      ],
      message1: '%1',
      args1: [{ type: 'input_statement', name: 'DO' }],
      colour: CATEGORY_COLOURS.control,
      previousStatement: null,
      nextStatement: null,
    },
  ]);
}

/** Bornes appliquees aux valeurs saisies, issues des limites partagees. */
export const FIELD_BOUNDS = {
  minDistance: SAFETY.motion.minDistancePerStepCm,
  maxDistance: SAFETY.motion.maxDistancePerStepCm,
  minAngle: SAFETY.motion.minAnglePerStepDeg,
  maxAngle: SAFETY.motion.maxAnglePerStepDeg,
  minWait: SAFETY.timing.minWaitSeconds,
  maxWait: SAFETY.timing.maxWaitSeconds,
  minRepeat: 1,
  maxRepeat: SAFETY.program.maxRepeatCount,
} as const;