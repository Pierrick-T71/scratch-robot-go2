import { describe, it, expect } from 'vitest';
import {
  durationForDistance,
  durationForAngle,
  moveTimeoutSeconds,
  forwardSetpoint,
  turnSetpoint,
  ZERO_VELOCITY,
  MOVE_LINEAR_SPEED_MPS,
  MOVE_ANGULAR_SPEED_RPS,
  distanceForDuration,
  MIN_MOVE_DURATION_SECONDS,
} from '../src/lib/robot/motion';
import { SAFETY } from '../src/lib/robot/limits';

describe('mouvement — durées nominales', () => {
  it('convertit une distance en durée à la vitesse configurée', () => {
    // 50 cm à 0.3 m/s => 0.5 / 0.3 ≈ 1.667 s
    expect(durationForDistance(50)).toBeCloseTo(0.5 / MOVE_LINEAR_SPEED_MPS, 5);
  });

  it('utilise la valeur absolue de la distance', () => {
    expect(durationForDistance(-50)).toBeCloseTo(durationForDistance(50), 10);
  });

  it('convertit un angle en durée', () => {
    const expected = (90 / (180 / Math.PI)) / MOVE_ANGULAR_SPEED_RPS;
    expect(durationForAngle(90)).toBeCloseTo(expected, 5);
  });

  it('ne descend jamais sous la durée minimale (protection div/0)', () => {
    expect(durationForDistance(0)).toBe(MIN_MOVE_DURATION_SECONDS);
    expect(durationForAngle(0)).toBe(MIN_MOVE_DURATION_SECONDS);
  });

  it('reste cohérent avec la distance parcourue pendant la durée', () => {
    const duration = durationForDistance(100);
    expect(distanceForDuration(duration)).toBeCloseTo(100, 6);
  });
});

describe('mouvement — consignes de vitesse', () => {
  it('avance avec une vitesse positive et recule avec une vitesse négative', () => {
    expect(forwardSetpoint(50)).toEqual({ vx: MOVE_LINEAR_SPEED_MPS, vy: 0, vyaw: 0 });
    expect(forwardSetpoint(-50)).toEqual({ vx: -MOVE_LINEAR_SPEED_MPS, vy: 0, vyaw: 0 });
  });

  it('tourne à gauche dans un sens et à droite dans l’autre', () => {
    expect(turnSetpoint(90).vyaw).toBe(MOVE_ANGULAR_SPEED_RPS);
    expect(turnSetpoint(-90).vyaw).toBe(-MOVE_ANGULAR_SPEED_RPS);
    // Une rotation pure ne doit jamais contenir de vitesse linéaire.
    expect(turnSetpoint(90).vx).toBe(0);
    expect(turnSetpoint(90).vy).toBe(0);
  });

  it('ne dépasse jamais la vitesse maximale autorisée', () => {
    expect(MOVE_LINEAR_SPEED_MPS).toBeLessThanOrEqual(SAFETY.motion.maxLinearSpeed);
    expect(MOVE_ANGULAR_SPEED_RPS).toBeLessThanOrEqual(SAFETY.motion.maxAngularSpeed);
  });

  it('expose une consigne nulle pour l’arrêt', () => {
    expect(ZERO_VELOCITY).toEqual({ vx: 0, vy: 0, vyaw: 0 });
  });
});

describe('mouvement — délai de sécurité', () => {
  it('accorde une marge au délai nominal', () => {
    const nominal = durationForDistance(50);
    expect(moveTimeoutSeconds({ distanceCm: 50 })).toBeGreaterThan(nominal);
  });

  it('donne un délai plus long pour un parcours plus long', () => {
    expect(moveTimeoutSeconds({ distanceCm: 150 })).toBeGreaterThan(
      moveTimeoutSeconds({ distanceCm: 50 }),
    );
  });
});