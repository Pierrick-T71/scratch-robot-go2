/**
 * Modele de mouvement : conversion distance/angle -> vitesse + duree.
 *
 * FAIT VERIFIE SUR LE SDK OFFICIEL : `SportClient.Move(vx, vy, vyaw)` prend
 * une VITESSE, pas une distance. Il n'existe aucune commande "avancer de N cm"
 * dans le SDK. Une distance doit donc etre reconstruite par le service, soit
 * en boucle fermee sur l'etat mesure (`rt/sportmodestate`), soit, a defaut,
 * par une duree calculee.
 *
 * CE QUE CES FONCTIONS NE FONT PAS :
 *  - elles ne garantissent pas qu'un deplacement est termine ;
 *  - elles ne garantissent pas l'absence de derive (glissement, obstacle) ;
 *  - elles ne constituent pas un arret physique.
 *
 * L'interface ne doit donc jamais afficher "c'est termine" sur la seule base
 * de cette duree. Seuls les retours mesures autorisent cette affirmation.
 */
import { SAFETY } from './limits';

/**
 * Vitesse lineaire effectivement commandee, en m/s.
 * Volontairement fixee a la limite validee des essais, pas plus.
 */
export const MOVE_LINEAR_SPEED_MPS = SAFETY.motion.maxLinearSpeed;

/**
 * Vitesse angulaire effectivement commandee, en rad/s.
 */
export const MOVE_ANGULAR_SPEED_RPS = SAFETY.motion.maxAngularSpeed;

/** Duree minimale d'un mouvement, en secondes (evite les divisions par zero). */
export const MIN_MOVE_DURATION_SECONDS = 0.05;

/** Duree minimale d'un mouvement, par pas de 10 cm / 15 deg. */
export const STEP_QUANTUM = { distanceCm: 10, angleDeg: 15 } as const;

const DEG_PER_RAD = 180 / Math.PI;

/** Duree nominale pour parcourir une distance, en secondes. */
export function durationForDistance(distanceCm: number, speedMps = MOVE_LINEAR_SPEED_MPS): number {
  const meters = Math.abs(distanceCm) / 100;
  return Math.max(MIN_MOVE_DURATION_SECONDS, meters / speedMps);
}

/** Duree nominale pour effectuer une rotation, en secondes. */
export function durationForAngle(angleDeg: number, speedRps = MOVE_ANGULAR_SPEED_RPS): number {
  const radians = Math.abs(angleDeg) / DEG_PER_RAD;
  return Math.max(MIN_MOVE_DURATION_SECONDS, radians / speedRps);
}

/** Duree nominale d'une instruction, en secondes. */
export function nominalDurationSeconds(params: {
  distanceCm?: number;
  angleDeg?: number;
}): number {
  if (params.distanceCm !== undefined) return durationForDistance(params.distanceCm);
  if (params.angleDeg !== undefined) return durationForAngle(params.angleDeg);
  return 0;
}

/**
 * Tolerance de fin de deplacement, en centimetres.
 * La boucle fermee du service s'arrete lorsque l'ecart est inferieur a ce
 * seuil ET que la vitesse mesuree est faible. Ces valeurs sont des choix
 * d'experience a confirmer sur robot reel.
 */
export const POSITION_TOLERANCE_CM = 5;

/** Tolerance de fin de rotation, en degres. */
export const YAW_TOLERANCE_DEG = 8;

/**
 * Marge ajoutee au delai nominal avant que le service ne declenche l'arret
 * de securite si la cible n'est pas atteinte. Un robot qui glisse ou bute
 * doit s'arreter, pas continuer a forcer.
 */
export const MOVE_TIMEOUT_MARGIN = 2.5;

/** Duree maximale d'une instruction de mouvement avant arret de securite. */
export function moveTimeoutSeconds(params: {
  distanceCm?: number;
  angleDeg?: number;
}): number {
  const nominal = nominalDurationSeconds(params);
  return nominal * MOVE_TIMEOUT_MARGIN + 1;
}

/**
 * Consigne de vitesse a publier pour un deplacement donne.
 * Renvoie les trois composantes attendues par `Move(vx, vy, vyaw)`.
 */
export interface VelocitySetpoint {
  vx: number;
  vy: number;
  vyaw: number;
}

export const ZERO_VELOCITY: VelocitySetpoint = { vx: 0, vy: 0, vyaw: 0 };

/** Consigne pour avancer / reculer de `distanceCm` (avant ou arriere du robot). */
export function forwardSetpoint(distanceCm: number): VelocitySetpoint {
  const sign = distanceCm >= 0 ? 1 : -1;
  return { vx: sign * MOVE_LINEAR_SPEED_MPS, vy: 0, vyaw: 0 };
}

/** Consigne pour tourner a gauche / a droite de `angleDeg`. */
export function turnSetpoint(angleDeg: number): VelocitySetpoint {
  const sign = angleDeg >= 0 ? 1 : -1;
  return { vx: 0, vy: 0, vyaw: sign * MOVE_ANGULAR_SPEED_RPS };
}

/**
 * Distance maximale qu'une vitesse donnee permet de parcourir pendant
 * `durationSeconds`. Utilise par le service pour detecter un depassement.
 */
export function distanceForDuration(durationSeconds: number, speedMps = MOVE_LINEAR_SPEED_MPS): number {
  return durationSeconds * speedMps * 100;
}