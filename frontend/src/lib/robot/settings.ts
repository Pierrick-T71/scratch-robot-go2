/**
 * Réglages de l'application.
 *
 * Deux catégories de réglages, à ne pas confondre :
 *
 *  1. Les **réglages adulte** (limites de mouvement, de durée, de distance),
 *     stockés CÔTÉ SERVICE et appliqués immédiatement. Le service reste
 *     l'autorité : le frontend ne fait que proposer.
 *
 *  2. Les **préférences d'affichage** (service utilisé, thème), stockées dans
 *     le navigateur et sans effet sur la sécurité.
 *
 * Les bornes (plancher / plafond) sont fournies par le service et ne sont
 * jamais calculées ici : l'interface ne peut pas s'attribuer de droits.
 */
import { SERVICE_URL } from './limits';

// --------------------------------------------------------------------------
// Réglages d'adulte
// --------------------------------------------------------------------------

export interface SettingBounds {
  min: number;
  max: number;
}

export interface SettingsBounds {
  [field: string]: SettingBounds;
}

export interface SettingsValues {
  [field: string]: number;
}

export interface SettingsPayload {
  values: SettingsValues;
  bounds: SettingsBounds;
}

/** Libellés et unités des réglages, dans l'ordre d'affichage. */
export interface SettingDescriptor {
  field: string;
  label: string;
  unit: string;
  /** aide courte affichée sous le champ */
  help: string;
  /** pas d'incrément du curseur */
  step: number;
}

export const SETTING_DESCRIPTORS: readonly SettingDescriptor[] = [
  {
    field: 'max_linear_speed',
    label: 'Vitesse maximale',
    unit: 'm/s',
    help: 'La vitesse à laquelle le robot peut avancer ou reculer.',
    step: 0.05,
  },
  {
    field: 'max_angular_speed',
    label: 'Rotation maximale',
    unit: 'rad/s',
    help: 'La vitesse à laquelle le robot peut tourner sur lui-même.',
    step: 0.05,
  },
  {
    field: 'max_distance_per_step_cm',
    label: 'Distance par déplacement',
    unit: 'cm',
    help: 'La distance maximale d’un seul bloc « Avancer » ou « Reculer ».',
    step: 10,
  },
  {
    field: 'max_angle_per_step_deg',
    label: 'Rotation par déplacement',
    unit: '°',
    help: 'L’angle maximal d’un seul bloc « Tourner ».',
    step: 15,
  },
  {
    field: 'max_wait_seconds',
    label: 'Attente maximale',
    unit: 's',
    help: 'La durée maximale d’un bloc « Attendre ».',
    step: 1,
  },
  {
    field: 'max_program_seconds',
    label: 'Durée totale du programme',
    unit: 's',
    help: 'Au-delà, le service arrête le programme pour sécurité.',
    step: 10,
  },
  {
    field: 'max_total_distance_cm',
    label: 'Distance totale',
    unit: 'cm',
    help: 'La somme de toutes les distances du programme.',
    step: 100,
  },
  {
    field: 'max_total_angle_deg',
    label: 'Rotations totales',
    unit: '°',
    help: 'La somme de tous les angles du programme.',
    step: 180,
  },
  {
    field: 'max_total_steps',
    label: 'Nombre de pas',
    unit: '',
    help: 'Le nombre maximum de blocs dans un programme.',
    step: 10,
  },
  {
    field: 'max_repeat_count',
    label: 'Répétitions par bloc',
    unit: '',
    help: 'Le nombre maximum de répétitions d’un bloc « Répéter ».',
    step: 1,
  },
];

// --------------------------------------------------------------------------
// Préférences d'affichage (navigateur)
// --------------------------------------------------------------------------

const PREFS_KEY = 'go2-scratch.prefs.v1';

export interface Preferences {
  /** Adresse du service robot, si différent de celle par défaut. */
  serviceUrl: string;
  /** Thème d'interface. */
  theme: 'clair' | 'sombre';
}

export const DEFAULT_PREFERENCES: Preferences = {
  serviceUrl: SERVICE_URL,
  theme: 'clair',
};

function isValidUrl(value: string): boolean {
  try {
    const url = new URL(value);
    return url.protocol === 'http:' || url.protocol === 'https:';
  } catch {
    return false;
  }
}

export function loadPreferences(): Preferences {
  try {
    const raw = globalThis.localStorage?.getItem(PREFS_KEY);
    if (!raw) return { ...DEFAULT_PREFERENCES };
    const parsed: unknown = JSON.parse(raw);
    if (typeof parsed !== 'object' || parsed === null) return { ...DEFAULT_PREFERENCES };

    const record = parsed as Record<string, unknown>;
    const url = typeof record['serviceUrl'] === 'string' ? record['serviceUrl'] : '';
    const theme = record['theme'];

    return {
      // Une URL invalide ou non http(s) est ignorée : elle ne doit pas
      // pouvoir rediriger les commandes vers un protocole dangereux.
      serviceUrl: isValidUrl(url) ? url : DEFAULT_PREFERENCES.serviceUrl,
      theme: theme === 'sombre' ? 'sombre' : 'clair',
    };
  } catch {
    return { ...DEFAULT_PREFERENCES };
  }
}

export function savePreferences(prefs: Preferences): void {
  if (!isValidUrl(prefs.serviceUrl)) {
    throw new Error('L’adresse du service doit commencer par http:// ou https://');
  }
  try {
    globalThis.localStorage?.setItem(PREFS_KEY, JSON.stringify(prefs));
  } catch {
    throw new Error('Impossible d’enregistrer les préférences sur cet appareil.');
  }
}