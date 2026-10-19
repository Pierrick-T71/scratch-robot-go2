/**
 * Validation avant exécution.
 *
 * Cette validation est un CONFORT pour l'enfant : retour immédiat, message
 * clair. Elle ne remplace pas le service, seul juge. Ces tests vérifient donc
 * ce qui est refusable sans exécuter le programme.
 */
import { describe, it, expect } from 'vitest';
import { validateProgram } from '../src/lib/robot/validate';
import { countSteps, estimateDuration, type Program, type Statement } from '../src/lib/robot/program';

const move = (seconds = 2, line = 1): Statement => ({
  kind: 'move',
  direction: 'forward',
  seconds,
  line,
});
const turn = (degrees = 90, line = 1): Statement => ({
  kind: 'turn',
  direction: 'left',
  degrees,
  line,
});
const wait = (seconds = 1, line = 1): Statement => ({ kind: 'wait', seconds, line });

const program = (...statements: Statement[]): Program => ({ statements });

/** Programme de référence : il doit toujours passer. */
const REFERENCE: Program = program(
  move(2),
  turn(90),
  move(2),
  { kind: 'stop_move', line: 4 },
);

describe('programme de référence', () => {
  it('est accepté', () => {
    const report = validateProgram(REFERENCE);
    expect(report.valid, report.issues.map((i) => i.message).join(' | ')).toBe(true);
  });

  it('est résumé correctement', () => {
    const report = validateProgram(REFERENCE);
    expect(report.summary.stepCount).toBe(4);
    // 2 s + 2 s + 90° (~3,1 s à 28,6 °/s)
    expect(report.summary.estimatedSeconds).toBeGreaterThan(6);
    expect(report.summary.estimatedSeconds).toBeLessThan(9);
  });
});

describe('structure', () => {
  it('refuse un programme vide', () => {
    const report = validateProgram(program());
    expect(report.valid).toBe(false);
    expect(report.issues.some((i) => i.message.includes('ne fait rien'))).toBe(true);
  });

  it('accepte un programme fait uniquement de structure', () => {
    // Un programme peut n'être fait que d'une boucle et d'un arrêt.
    const statements: Statement[] = [
      { kind: 'repeat', times: 2, body: [{ kind: 'stop_move', line: 1 }], line: 1 },
      { kind: 'stop_program', line: 2 },
    ];
    expect(validateProgram(program(...statements)).valid).toBe(true);
  });
});

describe('valeurs refusées', () => {
  it('refuse une durée absente des menus', () => {
    const report = validateProgram(program(move(0.25)));
    expect(report.valid).toBe(false);
  });

  it.each([1, 2, 3, 5])('accepte la durée %i s', (seconds) => {
    expect(validateProgram(program(move(seconds))).valid).toBe(true);
  });

  it.each([45, 90, 180])('accepte l’angle %i°', (degrees) => {
    expect(validateProgram(program(turn(degrees))).valid).toBe(true);
  });

  it('refuse un angle absent des menus', () => {
    expect(validateProgram(program(turn(37))).valid).toBe(false);
  });

  it('refuse un nombre de répétitions absent des menus', () => {
    const statements: Statement[] = [{ kind: 'repeat', times: 7, body: [], line: 1 }];
    expect(validateProgram(program(...statements)).valid).toBe(false);
  });
});

describe('cumuls', () => {
  it('refuse un programme trop long', () => {
    const many = Array.from({ length: 600 }, () => wait(1));
    expect(validateProgram(program(...many)).valid).toBe(false);
  });

  it('refuse un programme qui dure trop longtemps', () => {
    // 10 répétitions × 3 × 5 s = 150 s, au-delà des 120 s.
    const statements: Statement[] = [
      { kind: 'repeat', times: 10, body: [wait(5), wait(5), wait(5)], line: 1 },
    ];
    const report = validateProgram(program(...statements));
    expect(report.valid).toBe(false);
    expect(report.issues.some((i) => i.message.includes('trop longtemps'))).toBe(true);
  });

  it('refuse des répétitions trop imbriquées', () => {
    let body: Statement[] = [wait(1)];
    for (let i = 0; i < 5; i += 1) {
      body = [{ kind: 'repeat', times: 2, body, line: i }];
    }
    expect(validateProgram(program(...body)).valid).toBe(false);
  });
});

describe('conditions', () => {
  it('n’évalue PAS la condition', () => {
    // « la batterie est faible » ne peut pas être décidée ici : le service
    // seul détient la valeur lue. Le frontend ne doit donc rien signaler.
    const statements: Statement[] = [
      {
        kind: 'if',
        condition: 'battery_low',
        then: [move(2)],
        otherwise: [{ kind: 'stop_program', line: 2 }],
        line: 1,
      },
    ];
    expect(validateProgram(program(...statements)).valid).toBe(true);
  });

  it('refuse une condition qui n’est pas proposée', () => {
    const statements: Statement[] = [
      { kind: 'if', condition: 'obstacle_detected' as never, then: [], line: 1 },
    ];
    const report = validateProgram(program(...statements));
    expect(report.valid).toBe(false);
    expect(report.issues.some((i) => i.message.includes('n’est pas proposée'))).toBe(true);
  });

  it('vérifie les deux branches', () => {
    // Une condition bascule à n'importe quel moment : le « sinon » ne peut
    // pas être ignoré sous prétexte que « alors » est le pire cas.
    const statements: Statement[] = [
      {
        kind: 'if',
        condition: 'posture_stand',
        then: [move(2)],
        otherwise: [move(0.25)],
        line: 1,
      },
    ];
    expect(validateProgram(program(...statements)).valid).toBe(false);
  });
});

describe('programme.ts — calculs', () => {
  it('compte les répétitions développées', () => {
    const statements: Statement[] = [
      { kind: 'repeat', times: 5, body: [move(1), move(1)], line: 1 },
    ];
    expect(countSteps(statements)).toBe(10);
  });

  it('estime la durée d’une rotation', () => {
    // 90° à ~28,6 °/s ≈ 3,1 s.
    expect(estimateDuration([turn(90)])).toBeGreaterThan(3);
    expect(estimateDuration([turn(90)])).toBeLessThan(3.3);
  });

  it('retient la plus longue branche d’une condition', () => {
    const statements: Statement[] = [
      {
        kind: 'if',
        condition: 'posture_stand',
        then: [move(1)],
        otherwise: [move(5)],
        line: 1,
      },
    ];
    expect(estimateDuration(statements)).toBe(5);
  });
});