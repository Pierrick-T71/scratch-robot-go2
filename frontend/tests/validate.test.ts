import { describe, it, expect } from 'vitest';
import { validateCommands } from '../src/lib/robot/validate';
import { SAFETY } from '../src/lib/robot/limits';

const ALL = ['movement', 'posture', 'wait', 'stop'] as const;

describe('validation — structure', () => {
  it('refuse un programme vide', () => {
    const report = validateCommands([], ALL);
    expect(report.valid).toBe(false);
    expect(report.issues[0]?.message).toMatch(/ne fait rien/);
  });

  it('accepte un programme simple et cohérent', () => {
    const report = validateCommands(
      [
        { kind: 'stand_up' },
        { kind: 'move_forward', distanceCm: 50 },
        { kind: 'turn_left', angleDeg: 90 },
        { kind: 'wait', seconds: 1 },
      ],
      ALL,
    );
    expect(report.valid).toBe(true);
    expect(report.issues).toHaveLength(0);
    expect(report.summary.stepCount).toBe(4);
    expect(report.summary.totalDistanceCm).toBe(50);
    expect(report.summary.totalAngleDeg).toBe(90);
  });
});

describe('validation — plages de distance et d’angle', () => {
  it('refuse une distance trop courte', () => {
    const report = validateCommands([{ kind: 'move_forward', distanceCm: 1 }], ALL);
    expect(report.valid).toBe(false);
    expect(report.issues.some((i) => /entre .* cm/.test(i.message))).toBe(true);
  });

  it('refuse une distance trop longue', () => {
    const report = validateCommands(
      [{ kind: 'move_forward', distanceCm: SAFETY.motion.maxDistancePerStepCm + 1 }],
      ALL,
    );
    expect(report.valid).toBe(false);
  });

  it('accepte les bornes exactes', () => {
    const report = validateCommands(
      [
        { kind: 'move_forward', distanceCm: SAFETY.motion.minDistancePerStepCm },
        { kind: 'turn_right', angleDeg: SAFETY.motion.minAnglePerStepDeg },
      ],
      ALL,
    );
    expect(report.valid).toBe(true);
  });

  it('traite les valeurs négatives comme des valeurs absolues', () => {
    const report = validateCommands([{ kind: 'move_forward', distanceCm: -50 }], ALL);
    // La distance cumulee utilise la valeur absolue.
    expect(report.summary.totalDistanceCm).toBe(50);
    expect(report.valid).toBe(true);
  });

  it('refuse un angle hors plage', () => {
    const report = validateCommands([{ kind: 'turn_left', angleDeg: 5 }], ALL);
    expect(report.valid).toBe(false);
  });
});

describe('validation — durée d’attente', () => {
  it('refuse une attente nulle', () => {
    expect(validateCommands([{ kind: 'wait', seconds: 0 }], ALL).valid).toBe(false);
  });

  it('refuse une attente trop longue', () => {
    expect(
      validateCommands([{ kind: 'wait', seconds: SAFETY.timing.maxWaitSeconds + 1 }], ALL).valid,
    ).toBe(false);
  });
});

describe('validation — cumuls globaux', () => {
  it('refuse un programme dépassant le nombre maximal d’étapes', () => {
    const steps = Array.from({ length: SAFETY.program.maxTotalSteps + 1 }, () => ({
      kind: 'stop' as const,
    }));
    const report = validateCommands(steps, ALL);
    expect(report.valid).toBe(false);
    expect(report.issues.some((i) => /trop long/.test(i.message))).toBe(true);
  });

  it('refuse un programme dépassant la distance totale', () => {
    const step = SAFETY.motion.maxDistancePerStepCm;
    const count = Math.ceil(SAFETY.program.maxTotalDistanceCm / step) + 2;
    const steps = Array.from({ length: count }, () => ({
      kind: 'move_forward' as const,
      distanceCm: step,
    }));
    const report = validateCommands(steps, ALL);
    expect(report.valid).toBe(false);
    expect(report.issues.some((i) => /trop de distance/.test(i.message))).toBe(true);
  });

  it('refuse un programme dépassant la durée maximale', () => {
    const waits = Array.from({ length: SAFETY.program.maxTotalSteps }, () => ({
      kind: 'wait' as const,
      seconds: SAFETY.timing.maxWaitSeconds,
    }));
    const report = validateCommands(waits, ALL);
    expect(report.valid).toBe(false);
    expect(report.issues.some((i) => /trop longtemps/.test(i.message))).toBe(true);
  });
});

describe('validation — capacités disponibles', () => {
  it('refuse un mouvement quand la capacité est indisponible', () => {
    const report = validateCommands([{ kind: 'move_forward', distanceCm: 50 }], ['wait', 'stop']);
    expect(report.valid).toBe(false);
    expect(report.issues.some((i) => /n’est pas disponible/.test(i.message))).toBe(true);
  });

  it('autorise une posture quand seul le mouvement manque', () => {
    const report = validateCommands([{ kind: 'stand_up' }], ['posture']);
    expect(report.valid).toBe(true);
  });
});

describe('validation — résistance aux commandes forgées', () => {
  it('refuse un objet avec un genre inconnu injecté dans la liste', () => {
    // Simulation d'un client modifié : on caste car le type est statique.
    const forged = [{ kind: 'self_destruct' } as never];
    const report = validateCommands(forged, ALL);
    expect(report.valid).toBe(false);
    expect(report.issues.some((i) => /non reconnue/.test(i.message))).toBe(true);
  });
});