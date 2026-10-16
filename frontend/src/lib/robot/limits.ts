/**
 * Chargement des limites de securite depuis `shared/safety-limits.json`.
 *
 * Le MÊME fichier est lu par le robot-service (Python). C'est volontaire :
 * une seule source de verite, aucune derive possible entre l'interface et
 * l'autorite. Les verifications du frontend servent le retour immediat aux
 * enfants ; celles du service restent seules opposables.
 */
import raw from '../../../../shared/safety-limits.json';

export interface MotionLimits {
  maxLinearSpeed: number;
  maxAngularSpeed: number;
  maxDistancePerStepCm: number;
  maxAnglePerStepDeg: number;
  minDistancePerStepCm: number;
  minAnglePerStepDeg: number;
}

export interface TimingLimits {
  minWaitSeconds: number;
  maxWaitSeconds: number;
  commandTickSeconds: number;
  controlPeriodMs: number;
  safetyStopLatencyMs: number;
}

export interface ProgramLimits {
  maxTotalSteps: number;
  maxRepeatCount: number;
  maxNestedRepeatDepth: number;
  maxProgramSeconds: number;
  maxTotalDistanceCm: number;
  maxTotalAngleDeg: number;
}

export interface SafetyLimits {
  leaseTimeoutMs: number;
  heartbeatIntervalMs: number;
  frontendPollTimeoutMs: number;
  postStopVerificationMs: number;
  maxCommandRetries: number;
}

export interface ServiceConfig {
  host: string;
  port: number;
  allowedOrigin: string[];
}

export interface SafetyConfig {
  version: number;
  motion: MotionLimits;
  timing: TimingLimits;
  program: ProgramLimits;
  safety: SafetyLimits;
  service: ServiceConfig;
}

export const SAFETY: SafetyConfig = raw as SafetyConfig;

/** Base URL du robot-service. Injectee a la compilation, sinon valeur locale. */
export const SERVICE_URL: string =
  (import.meta.env['VITE_SERVICE_URL'] as string | undefined) ?? `http://127.0.0.1:8765`;