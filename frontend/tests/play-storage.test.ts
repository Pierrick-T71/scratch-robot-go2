/**
 * Sauvegarde locale du programme « Go2 Play ».
 *
 * L'enfant retrouve son programme en revenant ; et surtout, rien de ce qui est
 * relu n'est accepté sans vérification : un contenu bricolé ne doit jamais
 * produire un bloc inconnu ni une durée que le service refuserait.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';
import {
  MAX_BLOCKS,
  PlayStorageError,
  loadBlocks,
  parseBlock,
  saveBlocks,
  storageAvailable,
} from '../src/lib/play/storage';
import { createBlock, isAllowedDegrees, isAllowedDuration } from '../src/lib/play/blocks';

/** Faux stockage, contrôlable : on simule aussi la panne (quota, mode privé). */
function fakeStorage(): Storage {
  const map = new Map<string, string>();
  return {
    get length() {
      return map.size;
    },
    clear: () => map.clear(),
    getItem: (key: string) => map.get(key) ?? null,
    key: (index: number) => [...map.keys()][index] ?? null,
    removeItem: (key: string) => void map.delete(key),
    setItem: (key: string, value: string) => void map.set(key, value),
  };
}

beforeEach(() => {
  vi.stubGlobal('localStorage', fakeStorage());
});

describe('aller-retour', () => {
  it('retrouve les blocs et leurs réglages', () => {
    const blocks = [
      { ...createBlock('forward'), seconds: 3 },
      { ...createBlock('turn_right'), degrees: 180 },
      createBlock('sit'),
    ];
    saveBlocks(blocks);

    const reloaded = loadBlocks();
    expect(reloaded.map((block) => block.kind)).toEqual([
      'forward',
      'turn_right',
      'sit',
    ]);
    expect(reloaded[0]?.seconds).toBe(3);
    expect(reloaded[1]?.degrees).toBe(180);
  });

  it('donne un identifiant neuf à chaque rechargement', () => {
    saveBlocks([createBlock('forward')]);
    const first = loadBlocks();
    const second = loadBlocks();
    expect(first[0]?.id).not.toBe(second[0]?.id);
  });

  it('repart d’une page blanche sans sauvegarde', () => {
    expect(loadBlocks()).toEqual([]);
  });
});

describe('contenu non fiable', () => {
  it('ignore un contenu qui n’est pas une liste', () => {
    localStorage.setItem('go2-play.programme.v1', '{"kind":"forward"}');
    expect(loadBlocks()).toEqual([]);
  });

  it('ignore un texte qui n’est pas du JSON', () => {
    localStorage.setItem('go2-play.programme.v1', '<xml/>');
    expect(loadBlocks()).toEqual([]);
  });

  it('refuse un bloc inconnu sans perdre les autres', () => {
    localStorage.setItem(
      'go2-play.programme.v1',
      JSON.stringify([{ kind: 'fly', seconds: 2 }, { kind: 'sit' }]),
    );
    expect(loadBlocks().map((block) => block.kind)).toEqual(['sit']);
  });

  it('ramène une durée bricolée dans les bornes', () => {
    localStorage.setItem(
      'go2-play.programme.v1',
      JSON.stringify([{ kind: 'forward', seconds: 1.67 }, { kind: 'forward', seconds: 'x' }]),
    );
    const blocks = loadBlocks();
    expect(blocks).toHaveLength(2);
    for (const block of blocks) {
      expect(isAllowedDuration(block.seconds)).toBe(true);
    }
  });

  it('ramène un angle bricolé dans les bornes', () => {
    localStorage.setItem(
      'go2-play.programme.v1',
      JSON.stringify([{ kind: 'turn_right', degrees: 60 }, { kind: 'turn_left', degrees: 'x' }]),
    );
    const blocks = loadBlocks();
    expect(blocks).toHaveLength(2);
    for (const block of blocks) {
      expect(isAllowedDegrees(block.degrees)).toBe(true);
    }
  });

  it('ne garde pas plus de blocs que la limite', () => {
    const many = Array.from({ length: MAX_BLOCKS + 50 }, () => ({ kind: 'sit' }));
    localStorage.setItem('go2-play.programme.v1', JSON.stringify(many));
    expect(loadBlocks()).toHaveLength(MAX_BLOCKS);
  });

  it('lit un bloc isolé', () => {
    expect(parseBlock(null)).toBeNull();
    expect(parseBlock('sit')).toBeNull();
    expect(parseBlock({})).toBeNull();
    expect(parseBlock({ kind: 'balance' })?.kind).toBe('balance');
  });
});

describe('stockage indisponible', () => {
  it('signale l’échec d’écriture au lieu de le taire', () => {
    vi.stubGlobal('localStorage', {
      ...fakeStorage(),
      setItem: () => {
        throw new Error('quota');
      },
    } as Storage);
    expect(() => saveBlocks([createBlock('sit')])).toThrow(PlayStorageError);
  });

  it('ne casse pas la lecture quand le stockage refuse', () => {
    vi.stubGlobal('localStorage', {
      ...fakeStorage(),
      getItem: () => {
        throw new Error('mode privé');
      },
    } as Storage);
    expect(loadBlocks()).toEqual([]);
  });

  it('sait dire si le stockage existe', () => {
    expect(storageAvailable()).toBe(true);
    vi.stubGlobal('localStorage', undefined);
    expect(storageAvailable()).toBe(false);
  });
});
