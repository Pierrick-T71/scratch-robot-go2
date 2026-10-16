import { describe, it, expect, beforeEach } from 'vitest';
import {
  parseMission,
  saveMission,
  deleteMission,
  listMissions,
  MissionStorageError,
} from '../src/lib/programs/storage';

/** Faux localStorage minimal, suffisant pour les tests. */
class MemoryStorage {
  private data = new Map<string, string>();
  getItem(key: string): string | null {
    return this.data.get(key) ?? null;
  }
  setItem(key: string, value: string): void {
    this.data.set(key, value);
  }
  removeItem(key: string): void {
    this.data.delete(key);
  }
  clear(): void {
    this.data.clear();
  }
  key(i: number): string | null {
    return [...this.data.keys()][i] ?? null;
  }
  get length(): number {
    return this.data.size;
  }
}

const VALID_XML =
  '<xml><block type="go2_start"></block><block type="go2_stop"></block></xml>';

beforeEach(() => {
  Object.defineProperty(globalThis, 'localStorage', {
    value: new MemoryStorage(),
    configurable: true,
    writable: true,
  });
});

describe('missions — sauvegarde', () => {
  it('enregistre puis relit une mission', () => {
    const mission = saveMission('Tour du salon', VALID_XML);
    const list = listMissions();
    expect(list).toHaveLength(1);
    expect(list[0]?.name).toBe('Tour du salon');
    expect(list[0]?.id).toBe(mission.id);
  });

  it('met à jour une mission de même nom sans en créer de seconde', () => {
    saveMission('Mission A', VALID_XML);
    saveMission('Mission A', VALID_XML);
    const list = listMissions();
    expect(list).toHaveLength(1);
  });

  it('refuse un nom vide', () => {
    expect(() => saveMission('   ', VALID_XML)).toThrow(MissionStorageError);
  });

  it('refuse un nom trop long', () => {
    expect(() => saveMission('x'.repeat(61), VALID_XML)).toThrow(/60/);
  });

  it('refuse un programme qui n’est pas du XML Blockly', () => {
    expect(() => saveMission('Pirate', '<html><script></script></html>')).toThrow(
      MissionStorageError,
    );
  });
});

describe('missions — suppression', () => {
  it('supprime la bonne mission', () => {
    const a = saveMission('A', VALID_XML);
    saveMission('B', VALID_XML);
    deleteMission(a.id);
    const names = listMissions().map((m) => m.name);
    expect(names).toEqual(['B']);
  });
});

describe('missions — lecture de données non fiables', () => {
  it('refuse une mission sans nom', () => {
    expect(parseMission({ id: 'x', name: '', xml: VALID_XML })).toBeNull();
  });

  it('refuse une mission sans XML Blockly', () => {
    expect(parseMission({ id: 'x', name: 'N', xml: 'pas du xml' })).toBeNull();
  });

  it('refuse une version de schéma inconnue', () => {
    expect(
      parseMission({
        id: 'x',
        name: 'N',
        xml: VALID_XML,
        updatedAt: new Date().toISOString(),
        schemaVersion: 99,
      }),
    ).toBeNull();
  });

  it('refuse un XML surdimensionné', () => {
    const huge = `<xml>${'<block type="go2_stop"></block>'.repeat(20000)}</xml>`;
    expect(parseMission({ id: 'x', name: 'N', xml: huge })).toBeNull();
  });

  it('ignore silencieusement un stockage corrompu', () => {
    globalThis.localStorage.setItem('go2-scratch.missions.v1', '{ pas du json');
    expect(listMissions()).toEqual([]);
  });

  it('écarte les entrées invalides d’un stockage partiellement corrompu', () => {
    globalThis.localStorage.setItem(
      'go2-scratch.missions.v1',
      JSON.stringify([{ id: 'bon', name: 'Bonne', xml: VALID_XML, updatedAt: new Date().toISOString(), schemaVersion: 1 }, { id: 'mauvais' }]),
    );
    const list = listMissions();
    expect(list).toHaveLength(1);
    expect(list[0]?.name).toBe('Bonne');
  });
});