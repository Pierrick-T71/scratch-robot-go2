/**
 * Stockage local des missions (programmes Blockly).
 *
 * Aucun compte, aucun envoi reseau, aucun nom d'enfant : uniquement le
 * navigateur local (localStorage). Les donnees sont VALIDEES a la lecture
 * avant d'atteindre l'editeur ou le moteur - un fichier de programme externe
 * n'est jamais accepte tel quel.
 */
const STORAGE_KEY = 'go2-scratch.missions.v1';
const SCHEMA_VERSION = 1;

export interface Mission {
  id: string;
  name: string;
  /** Bloc de depart conserve pour le rendu. */
  hasStart: boolean;
  /** XML serialise Blockly. Valide a la lecture (taille + type de noeud). */
  xml: string;
  updatedAt: string;
  schemaVersion: number;
}

/** Taille maximale d'un programme stocke (garde-fou anti-depot massif). */
const MAX_XML_LENGTH = 300_000;
const MAX_NAME_LENGTH = 60;
const MAX_MISSIONS = 100;

export class MissionStorageError extends Error {}

/** Valide la forme d'une mission issue du stockage. */
export function parseMission(value: unknown): Mission | null {
  if (typeof value !== 'object' || value === null) return null;
  const raw = value as Record<string, unknown>;

  const id = raw['id'];
  const name = raw['name'];
  const xml = raw['xml'];
  const updatedAt = raw['updatedAt'];
  const schemaVersion = raw['schemaVersion'];

  if (typeof id !== 'string' || id.length === 0 || id.length > 64) return null;
  if (typeof name !== 'string' || name.length === 0 || name.trim().length === 0) return null;
  if (name.length > MAX_NAME_LENGTH) return null;
  if (typeof xml !== 'string' || xml.length === 0 || xml.length > MAX_XML_LENGTH) return null;
  if (typeof updatedAt !== 'string' || Number.isNaN(Date.parse(updatedAt))) return null;
  if (schemaVersion !== SCHEMA_VERSION) return null;
  if (!looksLikeBlocklyXml(xml)) return null;

  return { id, name: name.trim(), hasStart: true, xml, updatedAt, schemaVersion };
}

/** Verifie qu'une chaine ressemble a du XML Blockly, sans l'analyser entier. */
function looksLikeBlocklyXml(xml: string): boolean {
  const head = xml.slice(0, 400);
  if (!head.includes('<xml')) return false;
  if (!head.includes('</xml>') && !xml.includes('</xml>')) return false;
  return /<block\s+type="/.test(xml);
}

function readStore(): Mission[] {
  try {
    const rawText = globalThis.localStorage?.getItem(STORAGE_KEY);
    if (!rawText) return [];
    const parsed: unknown = JSON.parse(rawText);
    if (!Array.isArray(parsed)) return [];
    const missions: Mission[] = [];
    for (const entry of parsed) {
      const mission = parseMission(entry);
      if (mission) missions.push(mission);
    }
    return missions.slice(0, MAX_MISSIONS);
  } catch {
    // Stockage indisponible (mode prive) ou JSON corrompu : on repart vide.
    return [];
  }
}

function writeStore(missions: readonly Mission[]): void {
  try {
    globalThis.localStorage?.setItem(STORAGE_KEY, JSON.stringify(missions));
  } catch {
    throw new MissionStorageError('Impossible d’enregistrer la mission sur cet appareil.');
  }
}

export function listMissions(): Mission[] {
  return readStore().sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));
}

export function saveMission(name: string, xml: string): Mission {
  const trimmed = name.trim();
  if (trimmed.length === 0) {
    throw new MissionStorageError('Donne un nom à ta mission.');
  }
  if (trimmed.length > MAX_NAME_LENGTH) {
    throw new MissionStorageError(`Le nom doit faire moins de ${MAX_NAME_LENGTH} caractères.`);
  }
  if (!looksLikeBlocklyXml(xml)) {
    throw new MissionStorageError('Ce programme n’est pas valide.');
  }

  const missions = readStore();
  const existing = missions.find((m) => m.name.toLocaleLowerCase() === trimmed.toLocaleLowerCase());
  const mission: Mission = {
    id: existing?.id ?? createId(),
    name: trimmed,
    hasStart: true,
    xml: xml.slice(0, MAX_XML_LENGTH),
    updatedAt: new Date().toISOString(),
    schemaVersion: SCHEMA_VERSION,
  };

  const next = existing
    ? missions.map((m) => (m.id === existing.id ? mission : m))
    : [mission, ...missions];

  if (!existing && next.length > MAX_MISSIONS) {
    throw new MissionStorageError(`Tu ne peux pas garder plus de ${MAX_MISSIONS} missions.`);
  }

  writeStore(next);
  return mission;
}

export function deleteMission(id: string): void {
  writeStore(readStore().filter((m) => m.id !== id));
}

function createId(): string {
  const c: Crypto | undefined = globalThis.crypto;
  if (c && 'randomUUID' in c) return c.randomUUID();
  // Repli simple, suffisant pour un identifiant local.
  return `m-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}