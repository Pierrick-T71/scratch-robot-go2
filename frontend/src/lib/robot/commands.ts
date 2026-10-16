/**
 * Modele de commandes interne GO2 Scratch.
 *
 * IMPORTANT : ces noms sont un modele INTERNE du projet. Ce ne sont PAS des
 * methodes du SDK Unitree. Le robot-service est seul responsable de la
 * traduction vers l'API reelle du SDK (`SportClient.Move`, `StopMove`, ...).
 *
 * Aucune commande basse niveau (moteurs, CRC32, `rt/lowcmd`) n'est exposee.
 */

export const COMMAND_KINDS = [
  'move_forward',
  'move_backward',
  'turn_left',
  'turn_right',
  'wait',
  'stand_up',
  'sit_down',
  'stop',
] as const;

export type CommandKind = (typeof COMMAND_KINDS)[number];

/** Commandes qui declarent une distance en centimetres. */
export const DISTANCE_KINDS = ['move_forward', 'move_backward'] as const;
/** Commandes qui declarent un angle en degres. */
export const ANGLE_KINDS = ['turn_left', 'turn_right'] as const;
/** Commandes qui declarent une duree en secondes. */
export const TIME_KINDS = ['wait'] as const;

export type DistanceKind = (typeof DISTANCE_KINDS)[number];
export type AngleKind = (typeof ANGLE_KINDS)[number];
export type TimeKind = (typeof TIME_KINDS)[number];

export interface MoveCommand {
  kind: DistanceKind;
  /** Distance demandee, en centimetres. Valeur positive. */
  distanceCm: number;
}

export interface TurnCommand {
  kind: AngleKind;
  /** Angle demande, en degres. Valeur positive. */
  angleDeg: number;
}

export interface WaitCommand {
  kind: TimeKind;
  /** Duree d'attente, en secondes. */
  seconds: number;
}

/** Commandes instantanees : pas de distance, pas d'angle, pas de duree. */
export interface InstantCommand {
  kind: 'stand_up' | 'sit_down' | 'stop';
}

export type RobotCommand = MoveCommand | TurnCommand | WaitCommand | InstantCommand;

/** Les quatre capacites reelles exposees aux enfants. */
export type Capability = 'movement' | 'posture' | 'wait' | 'stop';

export const CAPABILITIES: readonly Capability[] = [
  'movement',
  'posture',
  'wait',
  'stop',
];

/** Correspondance commande -> capacite requise. */
export function capabilityOf(command: RobotCommand): Capability {
  switch (command.kind) {
    case 'move_forward':
    case 'move_backward':
    case 'turn_left':
    case 'turn_right':
      return 'movement';
    case 'stand_up':
    case 'sit_down':
      return 'posture';
    case 'wait':
      return 'wait';
    case 'stop':
      return 'stop';
  }
}

export function isCommandKind(value: unknown): value is CommandKind {
  return typeof value === 'string' && (COMMAND_KINDS as readonly string[]).includes(value);
}

/**
 * Verifie qu'un objet correspond a la forme d'une commande.
 * Utilise pour valider les donnees recues du reseau ou du stockage local :
 * on ne fait jamais confiance a une structure venue de l'exterieur.
 */
export function parseCommand(value: unknown): RobotCommand | null {
  if (typeof value !== 'object' || value === null) return null;
  const raw = value as Record<string, unknown>;
  const kind = raw['kind'];
  if (!isCommandKind(kind)) return null;

  const num = (key: string): number | null => {
    const v = raw[key];
    return typeof v === 'number' && Number.isFinite(v) ? v : null;
  };

  switch (kind) {
    case 'move_forward':
    case 'move_backward': {
      const distanceCm = num('distanceCm');
      return distanceCm === null ? null : { kind, distanceCm };
    }
    case 'turn_left':
    case 'turn_right': {
      const angleDeg = num('angleDeg');
      return angleDeg === null ? null : { kind, angleDeg };
    }
    case 'wait': {
      const seconds = num('seconds');
      return seconds === null ? null : { kind, seconds };
    }
    case 'stand_up':
    case 'sit_down':
    case 'stop':
      return { kind };
    default:
      return null;
  }
}

/** Nombre d'elements de la commande (pour les cumuls de distance / angle). */
export function distanceOf(command: RobotCommand): number {
  return command.kind === 'move_forward' || command.kind === 'move_backward'
    ? Math.abs(command.distanceCm)
    : 0;
}

export function angleOf(command: RobotCommand): number {
  return command.kind === 'turn_left' || command.kind === 'turn_right'
    ? Math.abs(command.angleDeg)
    : 0;
}