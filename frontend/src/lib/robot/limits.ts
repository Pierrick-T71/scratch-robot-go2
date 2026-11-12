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
 * Calcule l'URL de base du robot-service.
 *
 * Priorités :
 *  1. Injectée à la compilation (`VITE_SERVICE_URL`).
 *  2. Si la page est en HTTPS, sur un port standard (80/443), ou derrière un nom de domaine
 *     (ex: optimus.lecreusot.priv) : on utilise la même origine (`location.origin`)
 *     pour passer par le reverse-proxy (Nginx / Traefik) et éviter tout blocage Mixed Content.
 *  3. En développement local ou accès direct au robot sans reverse-proxy (ex: http://172.16.13.41:5173) :
 *     on vise le port 8765 sur le même hôte.
 *  4. Hors navigateur (tests node) : http://127.0.0.1:8765.
 */
export function computeServiceUrl(loc?: {
  protocol: string;
  hostname: string;
  port: string;
  origin: string;
}): string {
  const injected = import.meta.env['VITE_SERVICE_URL'] as string | undefined;
  if (injected) return injected;
  const current = loc ?? (typeof location !== 'undefined' ? location : undefined);
  if (current && current.hostname) {
    const isHttps = current.protocol === 'https:';
    const isStandardPort = current.port === '' || current.port === '80' || current.port === '443';
    const isDomain = current.hostname.includes('.') && !/^\d+\.\d+\.\d+\.\d+$/.test(current.hostname);

    if (isHttps || isStandardPort || isDomain) {
      return current.origin;
    }
    return `http://${current.hostname}:8765`;
  }
  return 'http://127.0.0.1:8765';
}

export const SERVICE_URL: string = computeServiceUrl();