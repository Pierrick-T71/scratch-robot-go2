/**
 * Définition des blocs GO2 Scratch (français).
 *
 * Chaque bloc est défini en JavaScript avec `init()`, pas en JSON.
 *
 * Pourquoi ? Le parseur JSON de Blockly 13 n'INSTANCIE PAS d'ombre
 * (`math_number`) : il accepte la clé `shadow` mais ne la consomme pas, et
 * `appendShadowInput()` / `setShadowInput()` n'existent pas dans cette
 * version. Un bloc déclaré en JSON affichait donc « Avancer **de** ␣ cm »,
 * avec une entrée vide et aucun nombre.
 *
 * La solution retenue est un champ numérique éditable placé directement dans
 * l'entrée du bloc : l'enfant clique sur le nombre et le modifie. C'est aussi
 * ce que fait le bloc `math_number` de Blockly, et c'est plus clair pour un
 * enfant de 10 ans qu'une ombre imbriquée.
 *
 * Convention de nommage interne (anglais) / libellé enfant (français).
 */
import * as Blockly from 'blockly/core';
import { SAFETY } from '../robot/limits';

const CATEGORY_COLOURS = {
  events: '#F2A33C',
  movement: '#3D7BFE',
  actions: '#12A57A',
  control: '#8E53D8',
} as const;

/** Nom du bloc de départ du programme. */
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
}

const KNOWN_BLOCKS = new Set<string>();

/** Registre des blocs autorisés. Toute entrée inconnue sera rejetée. */
export const BLOCK_DEFINITIONS: readonly BlockDefinition[] = [
  { type: START_BLOCK, category: 'events', colour: CATEGORY_COLOURS.events },
  { type: WAIT_BLOCK, category: 'events', colour: CATEGORY_COLOURS.events },
  { type: FORWARD_BLOCK, category: 'movement', colour: CATEGORY_COLOURS.movement },
  { type: BACKWARD_BLOCK, category: 'movement', colour: CATEGORY_COLOURS.movement },
  { type: TURN_LEFT_BLOCK, category: 'movement', colour: CATEGORY_COLOURS.movement },
  { type: TURN_RIGHT_BLOCK, category: 'movement', colour: CATEGORY_COLOURS.movement },
  { type: STOP_BLOCK, category: 'movement', colour: CATEGORY_COLOURS.movement },
  { type: STAND_UP_BLOCK, category: 'actions', colour: CATEGORY_COLOURS.actions },
  { type: SIT_DOWN_BLOCK, category: 'actions', colour: CATEGORY_COLOURS.actions },
  { type: REPEAT_BLOCK, category: 'control', colour: CATEGORY_COLOURS.control },
];

export function isKnownBlockType(type: string): boolean {
  return KNOWN_BLOCKS.has(type);
}

export const CATEGORIES = [
  { name: 'events', label: 'Quand ça commence', colour: CATEGORY_COLOURS.events },
  { name: 'movement', label: 'Déplacements', colour: CATEGORY_COLOURS.movement },
  { name: 'actions', label: 'Actions', colour: CATEGORY_COLOURS.actions },
  { name: 'control', label: 'Contrôle', colour: CATEGORY_COLOURS.control },
];

/** Valeurs par défaut affichées dans les blocs. */
const DEFAULTS = {
  distance: 50,
  angle: 90,
  wait: 2,
  repeat: 3,
} as const;

/**
 * Bornes posées sur les champs.
 *
 * Ce sont les **plafonds livrés** (valeurs de `shared/safety-limits.json`),
 * pas les réglages en vigueur : un curseur de saisie qui laisserait taper
 * 999999 serait pénible, mais les limites réellement applicables sont
 * validées par `validate.ts` ET par le service.
 */
const FIELD_BOUNDS = {
  distance: {
    min: SAFETY.motion.minDistancePerStepCm,
    max: SAFETY.motion.maxDistancePerStepCm,
  },
  angle: {
    min: SAFETY.motion.minAnglePerStepDeg,
    max: SAFETY.motion.maxAnglePerStepDeg,
  },
  wait: {
    min: SAFETY.timing.minWaitSeconds,
    max: SAFETY.timing.maxWaitSeconds,
  },
  repeat: { min: 1, max: SAFETY.program.maxRepeatCount },
} as const;

export { FIELD_BOUNDS };

/**
 * Ajoute un champ numérique borné dans une entrée, sous un NOM EXPLICITE.
 *
 * Le nom est indispensable : `Input.appendField(field)` sans nom donne
 * `field.name === undefined`, et le champ n'est alors **pas enregistré** dans
 * le bloc. Conséquence observée : `block.getFieldValue('DISTANCE')` renvoyait
 * `null` et le compilateur concluait « il manque un nombre » alors que le champ
 * était affiché à l'écran.
 *
 * `setMin()` et `setMax()` renvoient `void` dans Blockly 13 : on ne peut donc
 * pas les chaîner.
 */
function addNumber(
  input: Blockly.Input,
  name: string,
  value: number,
  min: number,
  max: number,
): void {
  const field = new Blockly.FieldNumber(value);
  field.setMin(min);
  field.setMax(max);
  input.appendField(field, name);
}

/**
 * Ajoute un texte à un bloc.
 *
 * `Block` n'a pas de `appendField()` : le texte passe par une entrée factice
 * (`dummy`). C'est la forme attendue par l'API JavaScript de Blockly.
 */
function addText(block: Blockly.Block, text: string): void {
  block.appendDummyInput().appendField(text);
}

/** Enregistre tous les blocs GO2 sur le namespace Blockly. Idempotent. */
export function registerGo2Blocks(): void {
  if (Blockly.Blocks[START_BLOCK] !== undefined) return;

  // --- Événements -----------------------------------------------------------

  Blockly.Blocks[START_BLOCK] = {
    init(this: Blockly.Block) {
      this.setStyle('hat_blocks');
      addText(this, 'Quand je clique sur Démarrer');
      this.setNextStatement(true);
      this.setColour(CATEGORY_COLOURS.events);
    },
  };

  Blockly.Blocks[WAIT_BLOCK] = {
    init(this: Blockly.Block) {
      const input = this.appendValueInput('DURATION').setCheck('Number');
      addNumber(input, 'DURATION', DEFAULTS.wait, FIELD_BOUNDS.wait.min, FIELD_BOUNDS.wait.max);
      addText(this, ' secondes');
      this.setInputsInline(false);
      this.setPreviousStatement(true);
      this.setNextStatement(true);
      this.setColour(CATEGORY_COLOURS.events);
    },
  };

  // --- Déplacements ---------------------------------------------------------

  Blockly.Blocks[FORWARD_BLOCK] = {
    init(this: Blockly.Block) {
      const input = this.appendValueInput('DISTANCE').setCheck('Number');
      addNumber(
        input,
        'DISTANCE',
        DEFAULTS.distance,
        FIELD_BOUNDS.distance.min,
        FIELD_BOUNDS.distance.max,
      );
      addText(this, ' cm');
      this.setInputsInline(false);
      this.setPreviousStatement(true);
      this.setNextStatement(true);
      this.setColour(CATEGORY_COLOURS.movement);
    },
  };

  Blockly.Blocks[BACKWARD_BLOCK] = {
    init(this: Blockly.Block) {
      const input = this.appendValueInput('DISTANCE').setCheck('Number');
      addNumber(
        input,
        'DISTANCE',
        DEFAULTS.distance,
        FIELD_BOUNDS.distance.min,
        FIELD_BOUNDS.distance.max,
      );
      addText(this, ' cm');
      this.setInputsInline(false);
      this.setPreviousStatement(true);
      this.setNextStatement(true);
      this.setColour(CATEGORY_COLOURS.movement);
    },
  };

  Blockly.Blocks[TURN_LEFT_BLOCK] = {
    init(this: Blockly.Block) {
      const input = this.appendValueInput('ANGLE').setCheck('Number');
      addNumber(input, 'ANGLE', DEFAULTS.angle, FIELD_BOUNDS.angle.min, FIELD_BOUNDS.angle.max);
      addText(this, ' degrés');
      this.setInputsInline(false);
      this.setPreviousStatement(true);
      this.setNextStatement(true);
      this.setColour(CATEGORY_COLOURS.movement);
    },
  };

  Blockly.Blocks[TURN_RIGHT_BLOCK] = {
    init(this: Blockly.Block) {
      const input = this.appendValueInput('ANGLE').setCheck('Number');
      addNumber(input, 'ANGLE', DEFAULTS.angle, FIELD_BOUNDS.angle.min, FIELD_BOUNDS.angle.max);
      addText(this, ' degrés');
      this.setInputsInline(false);
      this.setPreviousStatement(true);
      this.setNextStatement(true);
      this.setColour(CATEGORY_COLOURS.movement);
    },
  };

  Blockly.Blocks[STOP_BLOCK] = {
    init(this: Blockly.Block) {
      addText(this, "S'arrêter");
      this.setPreviousStatement(true);
      this.setNextStatement(true);
      this.setColour(CATEGORY_COLOURS.movement);
    },
  };

  // --- Actions ---------------------------------------------------------------

  Blockly.Blocks[STAND_UP_BLOCK] = {
    init(this: Blockly.Block) {
      addText(this, 'Se mettre debout');
      this.setPreviousStatement(true);
      this.setNextStatement(true);
      this.setColour(CATEGORY_COLOURS.actions);
    },
  };

  Blockly.Blocks[SIT_DOWN_BLOCK] = {
    init(this: Blockly.Block) {
      addText(this, "S'asseoir");
      this.setPreviousStatement(true);
      this.setNextStatement(true);
      this.setColour(CATEGORY_COLOURS.actions);
    },
  };

  // --- Contrôle --------------------------------------------------------------

  Blockly.Blocks[REPEAT_BLOCK] = {
    init(this: Blockly.Block) {
      const input = this.appendValueInput('COUNT').setCheck('Number');
      addNumber(input, 'COUNT', DEFAULTS.repeat, FIELD_BOUNDS.repeat.min, FIELD_BOUNDS.repeat.max);
      addText(this, ' fois');
      this.setInputsInline(false);
      this.appendStatementInput('DO');
      this.setPreviousStatement(true);
      this.setNextStatement(true);
      this.setColour(CATEGORY_COLOURS.control);
    },
  };

  for (const definition of BLOCK_DEFINITIONS) KNOWN_BLOCKS.add(definition.type);
}