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

/**
 * Base URL du robot-service.
 *
 * Injectée à la compilation (`VITE_SERVICE_URL`) — c'est la voie normale en
 * production. À défaut, on vise le même hôte que la page, port 8765 : ouvrir
 * l'interface depuis une autre machine du réseau doit fonctionner sans
 * reconstruire le bundle (sinon `127.0.0.1` désignerait le poste du visiteur,
 * pas le robot).
 */
function defaultServiceUrl(): string {
  const injected = import.meta.env['VITE_SERVICE_URL'] as string | undefined;
  if (injected) return injected;
  if (typeof location !== 'undefined' && location.hostname) {
    return `http://${location.hostname}:8765`;
  }
  return 'http://127.0.0.1:8765';
}

export const SERVICE_URL: string = defaultServiceUrl();