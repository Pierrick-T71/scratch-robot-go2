import { describe, it, expect } from 'vitest';
import {
  parseCommand,
  isCommandKind,
  capabilityOf,
  distanceOf,
  angleOf,
  COMMAND_KINDS,
} from '../src/lib/robot/commands';

describe('commandes — analyse', () => {
  it('accepte chaque genre de commande valide', () => {
    expect(parseCommand({ kind: 'move_forward', distanceCm: 50 })).toEqual({
      kind: 'move_forward',
      distanceCm: 50,
    });
    expect(parseCommand({ kind: 'turn_left', angleDeg: 90 })).toEqual({
      kind: 'turn_left',
      angleDeg: 90,
    });
    expect(parseCommand({ kind: 'wait', seconds: 2 })).toEqual({ kind: 'wait', seconds: 2 });
    expect(parseCommand({ kind: 'stop' })).toEqual({ kind: 'stop' });
    expect(parseCommand({ kind: 'stand_up' })).toEqual({ kind: 'stand_up' });
    expect(parseCommand({ kind: 'sit_down' })).toEqual({ kind: 'sit_down' });
  });

  it('refuse une commande inconnue', () => {
    expect(parseCommand({ kind: 'explode' })).toBeNull();
    expect(parseCommand({ kind: 'move' })).toBeNull();
    expect(isCommandKind('nuclear_launch')).toBe(false);
  });

  it('refuse une commande sans parametre obligatoire', () => {
    expect(parseCommand({ kind: 'move_forward' })).toBeNull();
    expect(parseCommand({ kind: 'turn_right' })).toBeNull();
    expect(parseCommand({ kind: 'wait' })).toBeNull();
  });

  it('refuse les valeurs non finies ou du mauvais type', () => {
    expect(parseCommand({ kind: 'move_forward', distanceCm: NaN })).toBeNull();
    expect(parseCommand({ kind: 'move_forward', distanceCm: Infinity })).toBeNull();
    expect(parseCommand({ kind: 'move_forward', distanceCm: '50' })).toBeNull();
    expect(parseCommand({ kind: 'wait', seconds: null })).toBeNull();
  });

  it('refuse les structures non-objet', () => {
    expect(parseCommand(null)).toBeNull();
    expect(parseCommand('avancer')).toBeNull();
    expect(parseCommand(42)).toBeNull();
    expect(parseCommand([])).toBeNull();
  });

  it('classe correctement les capacités', () => {
    expect(capabilityOf({ kind: 'move_forward', distanceCm: 10 })).toBe('movement');
    expect(capabilityOf({ kind: 'turn_left', angleDeg: 90 })).toBe('movement');
    expect(capabilityOf({ kind: 'stand_up' })).toBe('posture');
    expect(capabilityOf({ kind: 'wait', seconds: 1 })).toBe('wait');
    expect(capabilityOf({ kind: 'stop' })).toBe('stop');
  });

  it('cumule distances et angles', () => {
    expect(distanceOf({ kind: 'move_forward', distanceCm: 50 })).toBe(50);
    expect(distanceOf({ kind: 'turn_left', angleDeg: 90 })).toBe(0);
    expect(angleOf({ kind: 'turn_right', angleDeg: 45 })).toBe(45);
    expect(angleOf({ kind: 'wait', seconds: 1 })).toBe(0);
  });

  it('expose une liste de genres stable et non vide', () => {
    expect(COMMAND_KINDS.length).toBeGreaterThan(0);
    expect(new Set(COMMAND_KINDS).size).toBe(COMMAND_KINDS.length);
  });
});