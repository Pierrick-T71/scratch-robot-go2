/**
 * Sauvegarde locale du programme « Go2 Play ».
 *
 * Aucun compte, aucun envoi réseau : le navigateur seul. Et, comme pour les
 * missions Blockly, tout ce qui est relu est VALIDÉ : un contenu bricolé ne
 * doit jamais produire un bloc inconnu, une durée ou un angle hors bornes.
 */
import {
  clampDegrees,
  clampDuration,
  createBlock,
  isPlayBlockKind,
  type PlayBlock,
} from './blocks';

const STORAGE_KEY = 'go2-play.programme.v1';

/** Nombre maximal de blocs conservés (garde-fou anti-dépôt massif). */
export const MAX_BLOCKS = 200;

export class PlayStorageError extends Error {}

/** Vrai si le stockage local est utilisable (mode privé, quota…). */
export function storageAvailable(): boolean {
  try {
    return typeof globalThis.localStorage !== 'undefined';
  } catch {
    return false;
  }
}

/**
 * Relit un bloc venu du stockage.
 *
 * `null` si la forme est inconnue : on ne devine jamais un bloc.
 */
export function parseBlock(value: unknown): PlayBlock | null {
  if (typeof value !== 'object' || value === null) return null;
  const raw = value as Record<string, unknown>;
  if (!isPlayBlockKind(raw['kind'])) return null;

  // L'identifiant est refabriqué : deux rechargements ne doivent pas produire
  // deux blocs qui se croient identiques.
  const block = createBlock(raw['kind']);

  if (typeof raw['seconds'] === 'number' && Number.isFinite(raw['seconds'])) {
    block.seconds = clampDuration(raw['seconds']);
  }
  if (typeof raw['degrees'] === 'number' && Number.isFinite(raw['degrees'])) {
    block.degrees = clampDegrees(raw['degrees']);
  }

  return block;
}

export function loadBlocks(): PlayBlock[] {
  try {
    const text = globalThis.localStorage?.getItem(STORAGE_KEY);
    if (!text) return [];
    const parsed: unknown = JSON.parse(text);
    if (!Array.isArray(parsed)) return [];

    const blocks: PlayBlock[] = [];
    for (const entry of parsed.slice(0, MAX_BLOCKS)) {
      const block = parseBlock(entry);
      if (block) blocks.push(block);
    }
    return blocks;
  } catch {
    // Stockage indisponible ou contenu corrompu : on repart d'une page blanche.
    return [];
  }
}

export function saveBlocks(blocks: readonly PlayBlock[]): void {
  try {
    const payload = blocks
      .slice(0, MAX_BLOCKS)
      .map((block) => ({
        kind: block.kind,
        seconds: block.seconds,
        degrees: block.degrees,
      }));
    globalThis.localStorage?.setItem(STORAGE_KEY, JSON.stringify(payload));
  } catch {
    throw new PlayStorageError(
      'Impossible d’enregistrer le programme sur cet appareil.',
    );
  }
}

export function clearSavedBlocks(): void {
  try {
    globalThis.localStorage?.removeItem(STORAGE_KEY);
  } catch {
    /* rien à faire : l'absence de sauvegarde n'empêche pas de programmer */
  }
}
