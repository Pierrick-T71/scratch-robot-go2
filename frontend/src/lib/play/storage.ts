/**
 * Sauvegarde et importation du programme « Go2 Play » en JSON et localement.
 *
 * - Sauvegarde / Export en fichier JSON téléchargeable directement sur le PC hôte
 *   (dossier Téléchargements), compatible avec les blocs actuels et futurs.
 * - Réimportation directe depuis un fichier JSON hôte avec réhydratation complète.
 * - Sauvegarde locale synchrone (localStorage) pour conserver le travail en cours.
 * - Validation rigoureuse : durées et angles bornés, garde-fou anti-dépôt massif.
 */
import {
  clampDegrees,
  clampDuration,
  createBlock,
  DEFAULT_DEGREES,
  DEFAULT_SECONDS,
  isPlayBlockKind,
  type PlayBlock,
  type PlayBlockKind,
} from './blocks';

const STORAGE_KEY = 'go2-play.programme.v1';

/** Nombre maximal de blocs conservés (garde-fou anti-dépôt massif). */
export const MAX_BLOCKS = 200;

export class PlayStorageError extends Error {}

export interface ParseBlockOptions {
  /** Accepte un bloc même si son identifiant de type n'est pas dans les 12 blocs actuels. */
  allowFutureBlocks?: boolean;
}

/** Vrai si le stockage local est utilisable (mode privé, quota…). */
export function storageAvailable(): boolean {
  try {
    return typeof globalThis.localStorage !== 'undefined';
  } catch {
    return false;
  }
}

/**
 * Relit et valide un bloc issu du stockage ou d'un export JSON.
 *
 * `null` si la forme est inconnue : on ne devine jamais un bloc.
 * Conserve toutes les propriétés additionnelles pour assurer la pérennité
 * et l'extensibilité avec de futurs blocs.
 */
export function parseBlock(
  value: unknown,
  options?: ParseBlockOptions,
): PlayBlock | null {
  if (typeof value !== 'object' || value === null) return null;
  const raw = value as Record<string, unknown>;
  const rawKind = raw['kind'];
  if (typeof rawKind !== 'string' || rawKind.trim().length === 0) return null;

  const kind = rawKind.trim();
  const allowFuture = options?.allowFutureBlocks ?? false;

  if (!allowFuture && !isPlayBlockKind(kind)) {
    return null;
  }

  // L'identifiant est refabriqué si absent : deux rechargements ne doivent pas produire
  // deux blocs qui se croient identiques.
  const baseBlock = isPlayBlockKind(kind)
    ? createBlock(kind)
    : {
        id: `bloc-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`,
        kind: kind as PlayBlockKind,
        seconds: DEFAULT_SECONDS,
        degrees: DEFAULT_DEGREES,
      };

  const block: PlayBlock = {
    ...raw, // préserver toutes les propriétés pour les blocs futurs
    id: typeof raw['id'] === 'string' && raw['id'].length > 0 ? raw['id'] : baseBlock.id,
    kind: kind as PlayBlockKind,
    seconds:
      typeof raw['seconds'] === 'number' && Number.isFinite(raw['seconds'])
        ? clampDuration(raw['seconds'])
        : baseBlock.seconds,
    degrees:
      typeof raw['degrees'] === 'number' && Number.isFinite(raw['degrees'])
        ? clampDegrees(raw['degrees'])
        : baseBlock.degrees,
  };

  return block;
}

/**
 * Sérialise une liste de blocs au format JSON propre et prêt au partage ou stockage.
 * Préserve toutes les métadonnées et paramètres additionnels des blocs futurs.
 */
export function exportProgramToJson(blocks: readonly PlayBlock[]): string {
  const payload = {
    version: 1,
    generator: 'go2-play',
    savedAt: new Date().toISOString(),
    blocks: blocks.slice(0, MAX_BLOCKS).map((block) => {
      // Exclure l'id interne de session pour que l'export soit propre
      const { id, ...rest } = block;
      return rest;
    }),
  };
  return JSON.stringify(payload, null, 2);
}

/**
 * Déclenche le téléchargement immédiat du programme au format `.json` sur le PC hôte
 * (qui se place par défaut dans le dossier Téléchargements du navigateur).
 */
export function downloadProgramJson(
  blocks: readonly PlayBlock[],
  filename: string = 'programme-go2.json',
): void {
  try {
    const jsonStr = exportProgramToJson(blocks);
    if (typeof globalThis.document === 'undefined') {
      return;
    }
    const blob = new Blob([jsonStr], { type: 'application/json;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  } catch {
    throw new PlayStorageError(
      'Impossible de télécharger le fichier sur votre appareil.',
    );
  }
}

/**
 * Analyse et extrait une liste de blocs depuis une chaîne JSON importée.
 * Tolérant aux variations de schéma :
 * - `{ "version": 1, "blocks": [...] }`
 * - `{ "program": [...] }`
 * - `{ "statements": [...] }`
 * - Tableau direct `[...]`
 * Accepte les blocs connus et futurs en conservant l'intégralité de leurs paramètres.
 */
export function parseBlocksFromJson(jsonText: string): PlayBlock[] {
  let parsed: unknown;
  try {
    parsed = JSON.parse(jsonText);
  } catch {
    throw new PlayStorageError('Le fichier sélectionné n’est pas un JSON valide.');
  }

  let rawList: unknown[] = [];
  if (Array.isArray(parsed)) {
    rawList = parsed;
  } else if (typeof parsed === 'object' && parsed !== null) {
    const record = parsed as Record<string, unknown>;
    if (Array.isArray(record['blocks'])) {
      rawList = record['blocks'];
    } else if (Array.isArray(record['program'])) {
      rawList = record['program'];
    } else if (Array.isArray(record['statements'])) {
      rawList = record['statements'];
    } else {
      throw new PlayStorageError(
        'Le fichier JSON ne contient pas de liste de blocs reconnue.',
      );
    }
  } else {
    throw new PlayStorageError(
      'Format de programme JSON non reconnu.',
    );
  }

  const blocks: PlayBlock[] = [];
  for (const entry of rawList.slice(0, MAX_BLOCKS)) {
    let normalized = entry;
    // Traduction douce si l'entrée est au format instruction backend
    if (typeof entry === 'object' && entry !== null) {
      const e = entry as Record<string, unknown>;
      if (e['kind'] === 'move' && typeof e['direction'] === 'string') {
        normalized = { ...e, kind: e['direction'] };
      } else if (e['kind'] === 'turn' && typeof e['direction'] === 'string') {
        normalized = { ...e, kind: `turn_${e['direction']}` };
      } else if (e['kind'] === 'posture' && typeof e['posture'] === 'string') {
        normalized = { ...e, kind: e['posture'] };
      } else if (e['kind'] === 'gesture' && typeof e['gesture'] === 'string') {
        normalized = { ...e, kind: e['gesture'] };
      }
    }

    const block = parseBlock(normalized, { allowFutureBlocks: true });
    if (block) {
      blocks.push(block);
    }
  }

  return blocks;
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
      .map((block) => {
        const { id, ...rest } = block;
        return rest;
      });
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
