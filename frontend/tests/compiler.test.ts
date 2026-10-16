/**
 * Tests du compilateur de blocs.
 *
 * Ces tests montent un espace de travail Blockly « headless » (sans rendu
 * DOM) et vérifient la traduction blocs -> instructions.
 *
 * Régression couverte : les champs numériques des blocs GO2 sont enregistrés
 * sous un NOM EXPLICITE. Sans ce nom, `Input.appendField(field)` laisse
 * `field.name === undefined`, le champ n'est pas enregistré dans le bloc, et
 * le compilateur concluait « il manque un nombre » alors que le nombre était
 * affiché à l'écran.
 */
import { describe, it, expect, beforeAll } from 'vitest';
import * as Blockly from 'blockly/core';
import { registerGo2Blocks } from '../src/lib/blockly/blocks';
import {
  BACKWARD_BLOCK,
  FORWARD_BLOCK,
  REPEAT_BLOCK,
  SIT_DOWN_BLOCK,
  START_BLOCK,
  STAND_UP_BLOCK,
  STOP_BLOCK,
  TURN_LEFT_BLOCK,
  TURN_RIGHT_BLOCK,
  WAIT_BLOCK,
} from '../src/lib/blockly/blocks';
import { compileWorkspace } from '../src/lib/blockly/compiler';
import type { RobotCommand } from '../src/lib/robot/commands';

beforeAll(() => {
  registerGo2Blocks();
});

/** Crée un bloc détaché. */
function create(workspace: Blockly.Workspace, type: string): Blockly.Block {
  return workspace.newBlock(type);
}

/**
 * Accroche `after` à la suite de `before`.
 *
 * Le sens est contre-intuitif : on relie la sortie du bloc PRÉCÉDENT à
 * l'entrée du bloc SUIVANT.
 */
function chain(before: Blockly.Block, after: Blockly.Block): void {
  const connected = before.nextConnection?.connect(after.previousConnection);
  expect(connected, `${before.type} -> ${after.type}`).toBe(true);
}

function compile(workspace: Blockly.Workspace) {
  return compileWorkspace({
    getMainWorkspace: () => workspace,
  } as unknown as typeof Blockly);
}

describe('champs numériques des blocs', () => {
  const PARAMETERISED: Array<[string, string, number]> = [
    [FORWARD_BLOCK, 'DISTANCE', 50],
    [BACKWARD_BLOCK, 'DISTANCE', 50],
    [TURN_LEFT_BLOCK, 'ANGLE', 90],
    [TURN_RIGHT_BLOCK, 'ANGLE', 90],
    [WAIT_BLOCK, 'DURATION', 2],
    [REPEAT_BLOCK, 'COUNT', 3],
  ];

  it.each(PARAMETERISED)('%s expose un champ nommé %s', (type, field, expected) => {
    const block = new Blockly.Workspace().newBlock(type);
    // Sans nom explicite, le champ n'est PAS enregistré : c'est la régression.
    expect(block.getField(field), `${type}.${field} introuvable`).not.toBeNull();
    expect(block.getFieldValue(field)).toBe(expected);
  });

  it('la valeur saisie est lue par le compilateur', () => {
    const workspace = new Blockly.Workspace();
    const start = create(workspace, START_BLOCK);
    const forward = create(workspace, FORWARD_BLOCK);

    // ATTENTION : en Blockly 13 la signature est `setFieldValue(valeur, nom)`,
    // et non `setFieldValue(nom, valeur)` comme dans les versions antérieures.
    // L'ordre inverse lève « Field "137" not found ».
    forward.setFieldValue(137, 'DISTANCE');
    chain(start, forward);

    const result = compile(workspace);
    expect(result.commands).toEqual<RobotCommand[]>([
      { kind: 'move_forward', distanceCm: 137 },
    ]);
  });

  it('les blocs sans paramètre n’ont pas de champ de valeur', () => {
    const workspace = new Blockly.Workspace();
    for (const type of [START_BLOCK, STOP_BLOCK, STAND_UP_BLOCK, SIT_DOWN_BLOCK]) {
      const block = create(workspace, type);
      expect(block.getFieldValue('DISTANCE'), type).toBeNull();
      expect(block.getFieldValue('ANGLE'), type).toBeNull();
      expect(block.getFieldValue('DURATION'), type).toBeNull();
    }
  });
});

describe('compilation — séquence simple', () => {
  it('traduit une chaîne de blocs dans l’ordre', () => {
    const ws = new Blockly.Workspace();
    const start = create(ws, START_BLOCK);
    const stand = create(ws, STAND_UP_BLOCK);
    const forward = create(ws, FORWARD_BLOCK);
    const turn = create(ws, TURN_LEFT_BLOCK);
    const wait = create(ws, WAIT_BLOCK);
    const stop = create(ws, STOP_BLOCK);

    chain(start, stand);
    chain(stand, forward);
    chain(forward, turn);
    chain(turn, wait);
    chain(wait, stop);

    const result = compile(ws);
    expect(result.hasStart).toBe(true);
    expect(result.issues).toHaveLength(0);
    expect(result.commands).toEqual<RobotCommand[]>([
      { kind: 'stand_up' },
      { kind: 'move_forward', distanceCm: 50 },
      { kind: 'turn_left', angleDeg: 90 },
      { kind: 'wait', seconds: 2 },
      { kind: 'stop' },
    ]);
  });

  it('utilise les valeurs réellement saisies', () => {
    const ws = new Blockly.Workspace();
    const start = create(ws, START_BLOCK);
    const forward = create(ws, FORWARD_BLOCK);
    const wait = create(ws, WAIT_BLOCK);

    forward.setFieldValue(175, 'DISTANCE');
    wait.setFieldValue(7, 'DURATION');
    chain(start, forward);
    chain(forward, wait);

    const result = compile(ws);
    expect(result.commands).toEqual<RobotCommand[]>([
      { kind: 'move_forward', distanceCm: 175 },
      { kind: 'wait', seconds: 7 },
    ]);
  });

  it('signale un programme sans bloc de départ', () => {
    const ws = new Blockly.Workspace();
    create(ws, FORWARD_BLOCK);
    const result = compile(ws);
    expect(result.hasStart).toBe(false);
    expect(result.issues[0]?.message).toMatch(/bloc de départ/);
  });

  it('signale un bloc non rattaché', () => {
    const ws = new Blockly.Workspace();
    create(ws, START_BLOCK);
    create(ws, FORWARD_BLOCK); // flotte seul
    const result = compile(ws);
    expect(result.issues.some((i) => /seul/.test(i.message))).toBe(true);
  });
});

describe('compilation — répétitions', () => {
  /** Construit « START → REPEAT(COUNT) → DO » et renvoie le bloc interne. */
  function buildRepeat(ws: Blockly.Workspace, innerType: string) {
    const start = create(ws, START_BLOCK);
    const repeat = create(ws, REPEAT_BLOCK);
    const inner = create(ws, innerType);
    chain(start, repeat);
    // Entrée « statement » du bloc Répéter.
    expect(repeat.getInput('DO')?.connection.targetBlock()).toBeNull();
    expect(repeat.getInput('DO')?.connection.connect(inner.previousConnection)).toBe(true);
    return { start, repeat, inner };
  }

  it('aplatit une répétition en instructions', () => {
    const ws = new Blockly.Workspace();
    const { repeat } = buildRepeat(ws, FORWARD_BLOCK);
    expect(compile(ws).commands).toHaveLength(3); // 3 par défaut

    repeat.setFieldValue(4, 'COUNT');
    const result = compile(ws);
    expect(result.commands).toHaveLength(4);
    expect(result.commands.every((c) => c.kind === 'move_forward')).toBe(true);
  });

  it('respecte le nombre saisi', () => {
    const ws = new Blockly.Workspace();
    const { repeat } = buildRepeat(ws, TURN_LEFT_BLOCK);
    repeat.setFieldValue(5, 'COUNT');
    expect(compile(ws).commands).toHaveLength(5);
  });

  it('imbrique les répétitions', () => {
    const ws = new Blockly.Workspace();
    const start = create(ws, START_BLOCK);
    const outer = create(ws, REPEAT_BLOCK);
    const inner = create(ws, REPEAT_BLOCK);
    const move = create(ws, FORWARD_BLOCK);

    chain(start, outer);
    outer.getInput('DO')?.connection.connect(inner.previousConnection);
    inner.getInput('DO')?.connection.connect(move.previousConnection);
    outer.setFieldValue(2, 'COUNT');
    inner.setFieldValue(3, 'COUNT');

    // 2 × 3 = 6 déplacements.
    expect(compile(ws).commands).toHaveLength(6);
  });

  it('refuse un nombre de répétitions non entier', () => {
    const ws = new Blockly.Workspace();
    const { repeat } = buildRepeat(ws, FORWARD_BLOCK);
    repeat.setFieldValue(2.5, 'COUNT');

    const result = compile(ws);
    expect(result.commands).toHaveLength(0);
    expect(result.issues.some((i) => /entier/.test(i.message))).toBe(true);
  });

  it('ramène une répétition nulle à 1', () => {
    // Le champ est borné à 1 : un enfant ne peut pas saisir 0.
    // La garde du compilateur reste une défense pour les XML importés.
    const ws = new Blockly.Workspace();
    const { repeat } = buildRepeat(ws, FORWARD_BLOCK);
    repeat.setFieldValue(0, 'COUNT');
    expect(repeat.getFieldValue('COUNT')).toBe(1);
    expect(compile(ws).commands).toHaveLength(1);
  });
});

describe('compilation — robustesse', () => {
  it('ne boucle pas indéfiniment sur un cycle', () => {
    const ws = new Blockly.Workspace();
    const start = create(ws, START_BLOCK);
    const a = create(ws, FORWARD_BLOCK);
    const b = create(ws, WAIT_BLOCK);
    chain(start, a);
    chain(a, b);
    // Cycle délibéré. Blockly débranche le lien au départ pour l'accepter :
    // le programme devient simplement vide.
    b.nextConnection?.connect(a.previousConnection);

    // L'essentiel : la compilation se termine, sans boucle infinie.
    const result = compile(ws);
    expect(Array.isArray(result.commands)).toBe(true);
    expect(result.commands.length).toBeLessThan(3);
  });

  it('tolère une entrée vide', () => {
    const ws = new Blockly.Workspace();
    const start = create(ws, START_BLOCK);
    chain(start, create(ws, START_BLOCK));
    expect(() => compile(ws)).not.toThrow();
  });
});