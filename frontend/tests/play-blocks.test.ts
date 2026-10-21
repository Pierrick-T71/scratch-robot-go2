/**
 * Les douze blocs de « Go2 Play ».
 *
 * Ce qui est vérifié ici n'est pas cosmétique : c'est le contrat avec le
 * service. Un bloc dont la durée ou l'angle sort de ce que le service accepte
 * serait refusé au lancement — après que l'enfant a cru que c'était prêt.
 */
import { describe, it, expect } from 'vitest';
import {
  BLOCKS,
  DEGREES,
  DEFAULT_DEGREES,
  DEFAULT_SECONDS,
  DURATIONS,
  clampDegrees,
  clampDuration,
  createBlock,
  describeBlock,
  isAllowedDegrees,
  isAllowedDuration,
  isPlayBlockKind,
  specOf,
  toProgram,
  type PlayBlockKind,
} from '../src/lib/play/blocks';
import { validateProgram } from '../src/lib/robot/validate';

const KINDS: PlayBlockKind[] = [
  'forward',
  'backward',
  'turn_left',
  'turn_right',
  'sit',
  'stand',
  'balance',
  'lie_down',
  'heart',
  'jump',
  'salute',
  'stretch',
];

describe('catalogue', () => {
  it('ne contient que les douze blocs autorisés', () => {
    expect(BLOCKS.map((spec) => spec.kind)).toEqual(KINDS);
  });

  it('range chaque bloc dans une catégorie existante', () => {
    for (const spec of BLOCKS) {
      expect(['movement', 'actions']).toContain(spec.category);
      expect(spec.label.length).toBeGreaterThan(0);
      expect(spec.hint.length).toBeGreaterThan(0);
    }
  });

  it('propose un réglage pour les déplacements et les rotations', () => {
    const editable = BLOCKS.filter((spec) => spec.editable).map((spec) => [
      spec.kind,
      spec.editable,
    ]);
    expect(editable).toEqual([
      ['forward', 'seconds'],
      ['backward', 'seconds'],
      ['turn_left', 'degrees'],
      ['turn_right', 'degrees'],
    ]);
  });

  it('ne propose aucun réglage pour les postures', () => {
    for (const kind of [
      'sit',
      'stand',
      'balance',
      'lie_down',
      'heart',
      'jump',
      'salute',
      'stretch',
    ] as const) {
      expect(specOf(kind).editable).toBeUndefined();
    }
  });

  it('refuse un bloc inconnu', () => {
    expect(isPlayBlockKind('fly')).toBe(false);
    expect(isPlayBlockKind(42)).toBe(false);
    expect(() => specOf('fly' as PlayBlockKind)).toThrow();
  });
});

describe('durées', () => {
  it('n’accepte que les durées du service', () => {
    expect([...DURATIONS]).toEqual([1, 2, 3, 5]);
    expect(isAllowedDuration(4)).toBe(false);
    expect(isAllowedDuration(1.67)).toBe(false);
  });

  it('ramène une valeur libre sur la durée la plus proche', () => {
    expect(clampDuration(1.67)).toBe(2);
    expect(clampDuration(0)).toBe(1);
    expect(clampDuration(99)).toBe(5);
    expect(clampDuration(2)).toBe(2);
  });
});

describe('angles', () => {
  it('n’accepte que les angles du service', () => {
    expect([...DEGREES]).toEqual([45, 90, 180]);
    expect(isAllowedDegrees(60)).toBe(false);
    expect(isAllowedDegrees(0)).toBe(false);
  });

  it('ramène une valeur libre sur l’angle le plus proche', () => {
    expect(clampDegrees(60)).toBe(45);
    expect(clampDegrees(100)).toBe(90);
    expect(clampDegrees(179)).toBe(180);
    expect(clampDegrees(0)).toBe(45);
  });
});

describe('traduction en programme', () => {
  it('conserve l’ordre de la timeline', () => {
    const program = toProgram([
      createBlock('forward'),
      createBlock('turn_right'),
      createBlock('sit'),
    ]);
    expect(program.statements.map((statement) => statement.kind)).toEqual([
      'move',
      'turn',
      'posture',
    ]);
    expect(program.statements.map((statement) => statement.line)).toEqual([1, 2, 3]);
  });

  it('traduit chaque bloc en une instruction acceptée par la validation', () => {
    const blocks = KINDS.map((kind) => createBlock(kind));
    const report = validateProgram(toProgram(blocks));
    expect(report.issues).toEqual([]);
    expect(report.valid).toBe(true);
    expect(report.summary.stepCount).toBe(KINDS.length);
  });

  it('utilise la durée et l’angle choisis', () => {
    const forward = createBlock('forward');
    forward.seconds = 5;
    const backward = createBlock('backward');
    backward.seconds = 1;
    const left = createBlock('turn_left');
    left.degrees = 45;
    const right = createBlock('turn_right');
    right.degrees = 180;

    const program = toProgram([forward, backward, left, right]);
    expect(program.statements[0]).toMatchObject({
      kind: 'move',
      direction: 'forward',
      seconds: 5,
    });
    expect(program.statements[1]).toMatchObject({
      kind: 'move',
      direction: 'backward',
      seconds: 1,
    });
    expect(program.statements[2]).toMatchObject({
      kind: 'turn',
      direction: 'left',
      degrees: 45,
    });
    expect(program.statements[3]).toMatchObject({
      kind: 'turn',
      direction: 'right',
      degrees: 180,
    });
  });

  it('corrige une durée ou un angle bricolé hors bornes', () => {
    const forward = createBlock('forward');
    forward.seconds = 1.67; // valeur qu'aucun menu ne propose
    const turn = createBlock('turn_left');
    turn.degrees = 100;

    const program = toProgram([forward, turn]);
    expect(program.statements[0]).toMatchObject({
      seconds: DEFAULT_SECONDS,
    });
    expect(program.statements[1]).toMatchObject({
      degrees: DEFAULT_DEGREES,
    });
  });

  it('produit un programme vide quand la timeline est vide', () => {
    expect(toProgram([])).toEqual({ statements: [] });
  });

  it('traduit le geste « cœur » en instruction de geste', () => {
    const program = toProgram([createBlock('heart')]);
    expect(program.statements[0]).toMatchObject({
      kind: 'gesture',
      gesture: 'heart',
      line: 1,
    });
  });

  it('traduit « saluer » et « s’étirer » en instructions de geste', () => {
    const program = toProgram([createBlock('salute'), createBlock('stretch')]);
    expect(program.statements[0]).toMatchObject({
      kind: 'gesture',
      gesture: 'salute',
      line: 1,
    });
    expect(program.statements[1]).toMatchObject({
      kind: 'gesture',
      gesture: 'stretch',
      line: 2,
    });
  });

  it('traduit l’allongement et le saut', () => {
    const program = toProgram([createBlock('jump'), createBlock('lie_down')]);
    expect(program.statements[0]).toMatchObject({
      kind: 'gesture',
      gesture: 'jump',
    });
    expect(program.statements[1]).toMatchObject({
      kind: 'posture',
      posture: 'lie_down',
    });
  });
});

describe('description', () => {
  it('affiche la valeur choisie', () => {
    const forward = createBlock('forward');
    forward.seconds = 3;
    expect(describeBlock(forward)).toBe('Avancer de 3 s');

    const turn = createBlock('turn_right');
    turn.degrees = 180;
    expect(describeBlock(turn)).toBe('Tourner à droite 180°');

    expect(describeBlock(createBlock('sit'))).toBe('S’asseoir');
    expect(describeBlock(createBlock('salute'))).toBe('Saluer');
    expect(describeBlock(createBlock('stretch'))).toBe('S’étirer');
  });
});
