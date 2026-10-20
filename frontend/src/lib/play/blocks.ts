/**
 * « Go2 Play » — les sept blocs offerts à l'enfant.
 *
 * Volontairement réduit : quatre déplacements (avancer, reculer, tourner à
 * gauche, tourner à droite) et trois postures (s'asseoir, se mettre debout, se
 * stabiliser). Aucune variable, aucune expression, aucun capteur.
 *
 * ## Durées et angles, pas de centimètres
 *
 * Le SDK du Go2 ne sait pas « avancer de 50 cm » : il prend une VITESSE
 * (`Move(vx, vy, vyaw)`). Le service transforme donc une durée en consigne de
 * vitesse. Afficher des centimètres donnerait une précision que le robot ne
 * garantit pas — et le service n'accepte que 1, 2, 3 ou 5 secondes. L'enfant
 * choisit donc une durée, et le bloc le dit.
 *
 * L'angle, lui, est vérifiable : le cap (`yaw`) est une mesure réelle de
 * `SportModeState_`. Le service accepte 45°, 90° ou 180°.
 *
 * Les listes déroulantes proposent donc exactement les valeurs que le
 * service sait exécuter : pas une de plus (elle serait refusée au lancement),
 * pas une de moins (l'enfant n'aurait pas le choix).
 */
import type { Program, Statement } from '../robot/program';

export type PlayBlockKind =
  | 'forward'
  | 'backward'
  | 'turn_left'
  | 'turn_right'
  | 'sit'
  | 'stand'
  | 'balance';

export type PlayCategory = 'movement' | 'actions';

/** Tonalité pastel du bloc, alignée sur la charte graphique. */
export type BlockTone = 'blue' | 'violet' | 'peach' | 'mint';

/** Champ que l'enfant peut régler dans le bloc. */
export type EditableField = 'seconds' | 'degrees';

export interface PlayBlock {
  id: string;
  kind: PlayBlockKind;
  /** Durée choisie, en secondes (blocs de déplacement). */
  seconds: number;
  /** Angle choisi, en degrés (blocs de rotation). */
  degrees: number;
}

export interface BlockSpec {
  kind: PlayBlockKind;
  /** Texte du bloc, sans la valeur. */
  label: string;
  category: PlayCategory;
  tone: BlockTone;
  icon: string;
  /** Champ réglable, s'il y en a un. */
  editable?: EditableField;
  /** Phrase lue par les lecteurs d'écran. */
  hint: string;
}

/** Durées réellement acceptées par le service (allocation fixe). */
export const DURATIONS = [1, 2, 3, 5] as const;

/** Angles réellement acceptés par le service. */
export const DEGREES = [45, 90, 180] as const;

/** Valeur par défaut d'un nouveau bloc de déplacement. */
export const DEFAULT_SECONDS = 2;

/** Valeur par défaut d'un nouveau bloc de rotation. */
export const DEFAULT_DEGREES = 90;

/** Blocs de la catégorie « Mouvement » puis « Actions ». */
export const BLOCKS: readonly BlockSpec[] = [
  {
    kind: 'forward',
    label: 'Avancer de',
    category: 'movement',
    tone: 'blue',
    icon: 'arrow-right',
    editable: 'seconds',
    hint: 'Avancer pendant la durée choisie',
  },
  {
    kind: 'backward',
    label: 'Reculer',
    category: 'movement',
    tone: 'blue',
    icon: 'arrow-left',
    editable: 'seconds',
    hint: 'Reculer pendant la durée choisie',
  },
  {
    kind: 'turn_left',
    label: 'Tourner à gauche',
    category: 'movement',
    tone: 'violet',
    icon: 'turn-left',
    editable: 'degrees',
    hint: 'Tourner à gauche de l’angle choisi',
  },
  {
    kind: 'turn_right',
    label: 'Tourner à droite',
    category: 'movement',
    tone: 'violet',
    icon: 'turn-right',
    editable: 'degrees',
    hint: 'Tourner à droite de l’angle choisi',
  },
  {
    kind: 'sit',
    label: 'S’asseoir',
    category: 'actions',
    tone: 'peach',
    icon: 'sit',
    hint: 'Le robot s’assoit',
  },
  {
    kind: 'stand',
    label: 'Se mettre debout',
    category: 'actions',
    tone: 'peach',
    icon: 'stand',
    hint: 'Le robot se remet debout',
  },
  {
    kind: 'balance',
    label: 'Se stabiliser',
    category: 'actions',
    tone: 'mint',
    icon: 'balance',
    hint: 'Le robot se stabilise sur ses quatre pattes',
  },
];

const SPECS = new Map<PlayBlockKind, BlockSpec>(
  BLOCKS.map((spec) => [spec.kind, spec]),
);

export function specOf(kind: PlayBlockKind): BlockSpec {
  const spec = SPECS.get(kind);
  if (!spec) throw new Error(`Bloc inconnu : ${kind}`);
  return spec;
}

export function isPlayBlockKind(value: unknown): value is PlayBlockKind {
  return typeof value === 'string' && SPECS.has(value as PlayBlockKind);
}

/** Vrai si la durée fait partie des valeurs acceptées par le service. */
export function isAllowedDuration(value: number): boolean {
  return (DURATIONS as readonly number[]).includes(value);
}

/** Vrai si l'angle fait partie des valeurs acceptées par le service. */
export function isAllowedDegrees(value: number): boolean {
  return (DEGREES as readonly number[]).includes(value);
}

/** Ramène une valeur quelconque sur la valeur acceptée la plus proche. */
function clampTo<T extends number>(
  value: number,
  allowed: readonly T[],
  fallback: T,
): T {
  if ((allowed as readonly number[]).includes(value)) return value as T;
  let best = fallback;
  let bestGap = Infinity;
  for (const candidate of allowed) {
    const gap = Math.abs(candidate - value);
    if (gap < bestGap) {
      best = candidate;
      bestGap = gap;
    }
  }
  return best;
}

/** Ramène une durée sur une valeur que le service accepte. */
export function clampDuration(value: number): number {
  return clampTo(value, DURATIONS, DEFAULT_SECONDS);
}

/** Ramène un angle sur une valeur que le service accepte. */
export function clampDegrees(value: number): number {
  return clampTo(value, DEGREES, DEFAULT_DEGREES);
}

let counter = 0;

/** Fabrique un bloc neuf, avec un identifiant unique pour la session. */
export function createBlock(kind: PlayBlockKind): PlayBlock {
  counter += 1;
  return {
    id: `bloc-${Date.now().toString(36)}-${counter}`,
    kind,
    seconds: DEFAULT_SECONDS,
    degrees: DEFAULT_DEGREES,
  };
}

/**
 * Traduit la liste horizontale en programme pour le service.
 *
 * Une ligne = une position dans la timeline. L'ordre visuel est l'ordre
 * d'exécution : ce que l'enfant voit est exactement ce qui part.
 */
export function toProgram(blocks: readonly PlayBlock[]): Program {
  const statements: Statement[] = blocks.map((block, index) => {
    const line = index + 1;
    switch (block.kind) {
      case 'forward':
        return {
          kind: 'move',
          direction: 'forward',
          seconds: clampDuration(block.seconds),
          line,
        };
      case 'backward':
        return {
          kind: 'move',
          direction: 'backward',
          seconds: clampDuration(block.seconds),
          line,
        };
      case 'turn_left':
        return {
          kind: 'turn',
          direction: 'left',
          degrees: clampDegrees(block.degrees),
          line,
        };
      case 'turn_right':
        return {
          kind: 'turn',
          direction: 'right',
          degrees: clampDegrees(block.degrees),
          line,
        };
      case 'sit':
        return { kind: 'posture', posture: 'sit', line };
      case 'stand':
        return { kind: 'posture', posture: 'stand', line };
      case 'balance':
        return { kind: 'posture', posture: 'balance', line };
    }
  });

  return { statements };
}

/** Description courte, pour les messages et les tests. */
export function describeBlock(block: PlayBlock): string {
  const spec = specOf(block.kind);
  if (spec.editable === 'seconds') {
    return `${spec.label} ${clampDuration(block.seconds)} s`;
  }
  if (spec.editable === 'degrees') {
    return `${spec.label} ${clampDegrees(block.degrees)}°`;
  }
  return spec.label;
}
