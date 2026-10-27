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
  downloadProgramJson,
  exportProgramToJson,
  loadBlocks,
  parseBlock,
  parseBlocksFromJson,
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

describe('sauvegarde et import JSON (téléchargement et réimportation hôte)', () => {
  it('exporte un programme au format JSON propre', () => {
    const blocks = [
      { ...createBlock('forward'), seconds: 3 },
      { ...createBlock('turn_left'), degrees: 45 },
      createBlock('sit'),
    ];
    const jsonStr = exportProgramToJson(blocks);
    const parsed = JSON.parse(jsonStr);

    expect(parsed.version).toBe(1);
    expect(parsed.generator).toBe('go2-play');
    expect(typeof parsed.savedAt).toBe('string');
    expect(parsed.blocks).toHaveLength(3);
    expect(parsed.blocks[0]).toMatchObject({ kind: 'forward', seconds: 3 });
    expect(parsed.blocks[1]).toMatchObject({ kind: 'turn_left', degrees: 45 });
    expect(parsed.blocks[2]).toMatchObject({ kind: 'sit' });
  });

  it('réimporte un programme structuré avec ses réglages', () => {
    const jsonStr = JSON.stringify({
      version: 1,
      generator: 'go2-play',
      blocks: [
        { kind: 'backward', seconds: 5 },
        { kind: 'turn_right', degrees: 180 },
        { kind: 'lie_down' },
      ],
    });

    const imported = parseBlocksFromJson(jsonStr);
    expect(imported).toHaveLength(3);
    expect(imported[0]?.kind).toBe('backward');
    expect(imported[0]?.seconds).toBe(5);
    expect(imported[1]?.kind).toBe('turn_right');
    expect(imported[1]?.degrees).toBe(180);
    expect(imported[2]?.kind).toBe('lie_down');
  });

  it('accepte et préserve les blocs futurs et leurs paramètres additionnels', () => {
    const jsonStr = JSON.stringify({
      version: 2,
      blocks: [
        { kind: 'forward', seconds: 2 },
        {
          kind: 'dance_twist',
          tempo: 120,
          repeat: 4,
          style: 'funky',
        },
      ],
    });

    const imported = parseBlocksFromJson(jsonStr);
    expect(imported).toHaveLength(2);
    expect(imported[0]?.kind).toBe('forward');
    expect(imported[1]?.kind).toBe('dance_twist');
    expect((imported[1] as any).tempo).toBe(120);
    expect((imported[1] as any).repeat).toBe(4);
    expect((imported[1] as any).style).toBe('funky');

    // Vérifie aussi que l'export préserve ces futurs champs
    const reExported = JSON.parse(exportProgramToJson(imported));
    expect(reExported.blocks[1]).toMatchObject({
      kind: 'dance_twist',
      tempo: 120,
      repeat: 4,
      style: 'funky',
    });
  });

  it('accepte un tableau JSON direct', () => {
    const jsonStr = JSON.stringify([
      { kind: 'forward', seconds: 1 },
      { kind: 'sit' },
    ]);
    const imported = parseBlocksFromJson(jsonStr);
    expect(imported.map((b) => b.kind)).toEqual(['forward', 'sit']);
  });

  it('traduit les formats statements backend lors de l’import', () => {
    const jsonStr = JSON.stringify({
      statements: [
        { kind: 'move', direction: 'forward', seconds: 3 },
        { kind: 'turn', direction: 'left', degrees: 90 },
        { kind: 'posture', posture: 'sit' },
        { kind: 'gesture', gesture: 'heart' },
      ],
    });
    const imported = parseBlocksFromJson(jsonStr);
    expect(imported.map((b) => b.kind)).toEqual([
      'forward',
      'turn_left',
      'sit',
      'heart',
    ]);
    expect(imported[0]?.seconds).toBe(3);
    expect(imported[1]?.degrees).toBe(90);
  });

  it('lève une PlayStorageError si le JSON est corrompu', () => {
    expect(() => parseBlocksFromJson('ceci n est pas du json')).toThrow(
      PlayStorageError,
    );
    expect(() => parseBlocksFromJson('{"inconnu": 123}')).toThrow(
      PlayStorageError,
    );
  });

  it('déclenche le téléchargement du fichier JSON', () => {
    const blocks = [{ ...createBlock('forward'), seconds: 2 }];
    const appended: any[] = [];
    const removed: any[] = [];
    let clickCalled = false;

    const fakeAnchor: any = {
      click: () => {
        clickCalled = true;
      },
      download: '',
      href: '',
    };

    const fakeDoc: any = {
      body: {
        appendChild: (node: any) => {
          appended.push(node);
          return node;
        },
        removeChild: (node: any) => {
          removed.push(node);
          return node;
        },
      },
      createElement: () => fakeAnchor,
    };

    vi.stubGlobal('document', fakeDoc);
    vi.stubGlobal('URL', {
      createObjectURL: vi.fn(() => 'blob:fake-url'),
      revokeObjectURL: vi.fn(),
    });

    downloadProgramJson(blocks, 'mon-programme.json');

    expect(clickCalled).toBe(true);
    expect(appended).toHaveLength(1);
    expect(appended[0].download).toBe('mon-programme.json');
    expect(removed).toHaveLength(1);
  });
});
