/**
 * Validation des instructions avant envoi au service.
 *
 * Cette validation est un confort pour l'enfant (retour immediat, message
 * clair). Elle NE REMPLACE PAS la validation du robot-service, qui reste la
 * seule autorite opposable : un client modifie ne peut pas la contourner.
 */
import { SAFETY } from './limits';
import type { RobotCommand } from './commands';
import {
  capabilityOf,
  type Capability,
} from './commands';

export interface ValidationIssue {
  message: string;
  /** Index de l'instruction fautive dans la liste. */
  index?: number;
}

export interface ValidationReport {
  valid: boolean;
  issues: ValidationIssue[];
  /** Resume lisible du programme. */
  summary: ProgramSummary;
}

export interface ProgramSummary {
  stepCount: number;
  totalDistanceCm: number;
  totalAngleDeg: number;
  /** Duree estimee, en secondes. */
  estimatedSeconds: number;
  capabilities: Capability[];
}

function outOfRange(value: number, min: number, max: number): boolean {
  return value < min || value > max;
}

/**
 * Valide une liste d'instructions.
 *
 * @param commands instructions compilees
 * @param available capacites reellement offertes par l'adaptateur actif
 */
/**
 * Limites effectivement en vigueur.
 *
 * `overrides` vient du service (réglages d'adulte). Le fichier partagé reste
 * le plafond de référence : un champ absent utilise la valeur du fichier.
 */
function resolveLimits(overrides?: Readonly<Record<string, number>>): {
  motion: typeof SAFETY.motion;
  program: typeof SAFETY.program;
  timing: typeof SAFETY.timing;
} {
  const pick = (field: string, fallback: number): number => {
    const value = overrides?.[field];
    return typeof value === 'number' && Number.isFinite(value) ? value : fallback;
  };

  return {
    motion: {
      ...SAFETY.motion,
      maxLinearSpeed: pick('max_linear_speed', SAFETY.motion.maxLinearSpeed),
      maxAngularSpeed: pick('max_angular_speed', SAFETY.motion.maxAngularSpeed),
      maxDistancePerStepCm: pick(
        'max_distance_per_step_cm',
        SAFETY.motion.maxDistancePerStepCm,
      ),
      maxAnglePerStepDeg: pick('max_angle_per_step_deg', SAFETY.motion.maxAnglePerStepDeg),
    },
    timing: {
      ...SAFETY.timing,
      maxWaitSeconds: pick('max_wait_seconds', SAFETY.timing.maxWaitSeconds),
    },
    program: {
      ...SAFETY.program,
      maxTotalSteps: pick('max_total_steps', SAFETY.program.maxTotalSteps),
      maxProgramSeconds: pick('max_program_seconds', SAFETY.program.maxProgramSeconds),
      maxTotalDistanceCm: pick('max_total_distance_cm', SAFETY.program.maxTotalDistanceCm),
      maxTotalAngleDeg: pick('max_total_angle_deg', SAFETY.program.maxTotalAngleDeg),
    },
  };
}

export function validateCommands(
  commands: readonly RobotCommand[],
  available: readonly Capability[] = ['movement', 'posture', 'wait', 'stop'],
  overrides?: Readonly<Record<string, number>>,
): ValidationReport {
  const issues: ValidationIssue[] = [];
  const { motion, program, timing } = resolveLimits(overrides);

  let totalDistanceCm = 0;
  let totalAngleDeg = 0;
  let estimatedSeconds = 0;
  const capabilities = new Set<Capability>();

  if (commands.length === 0) {
    issues.push({ message: 'Ton programme ne fait rien. Ajoute un bloc sous le bloc de départ.' });
  }

  if (commands.length > program.maxTotalSteps) {
    issues.push({
      message: `Ton programme est trop long (${commands.length} pas). Maximum ${program.maxTotalSteps} pas.`,
    });
  }

  commands.forEach((command, index) => {
    capabilities.add(capabilityOf(command));

    switch (command.kind) {
      case 'move_forward':
      case 'move_backward': {
        const d = Math.abs(command.distanceCm);
        if (outOfRange(d, motion.minDistancePerStepCm, motion.maxDistancePerStepCm)) {
          issues.push({
            message: `Un déplacement doit faire entre ${motion.minDistancePerStepCm} et ${motion.maxDistancePerStepCm} cm. Ici : ${formatNumber(d)} cm.`,
            index,
          });
        }
        totalDistanceCm += d;
        estimatedSeconds += d / 100 / motion.maxLinearSpeed;
        break;
      }
      case 'turn_left':
      case 'turn_right': {
        const a = Math.abs(command.angleDeg);
        if (outOfRange(a, motion.minAnglePerStepDeg, motion.maxAnglePerStepDeg)) {
          issues.push({
            message: `Un tour doit faire entre ${motion.minAnglePerStepDeg} et ${motion.maxAnglePerStepDeg} degrés. Ici : ${formatNumber(a)} degrés.`,
            index,
          });
        }
        totalAngleDeg += a;
        estimatedSeconds += a / ((motion.maxAngularSpeed * 180) / Math.PI);
        break;
      }
      case 'wait': {
        if (outOfRange(command.seconds, SAFETY.timing.minWaitSeconds, timing.maxWaitSeconds)) {
          issues.push({
            message: `Une attente doit faire entre ${SAFETY.timing.minWaitSeconds} et ${formatNumber(timing.maxWaitSeconds)} secondes.`,
            index,
          });
        }
        estimatedSeconds += Math.max(0, command.seconds);
        break;
      }
      case 'stand_up':
      case 'sit_down':
      case 'stop':
        break;
      default: {
        const exhaustive: never = command;
        issues.push({
          message: `Instruction non reconnue : ${JSON.stringify(exhaustive)}`,
          index,
        });
      }
    }

    if (!available.includes(capabilityOf(command))) {
      issues.push({
        message: `L’action « ${labelOf(command.kind)} » n’est pas disponible dans ce mode.`,
        index,
      });
    }
  });

  if (totalDistanceCm > program.maxTotalDistanceCm) {
    issues.push({
      message: `Ton programme demande trop de distance (${formatNumber(totalDistanceCm)} cm). Maximum ${formatNumber(program.maxTotalDistanceCm)} cm.`,
    });
  }
  if (totalAngleDeg > program.maxTotalAngleDeg) {
    issues.push({
      message: `Ton programme demande trop de rotations (${formatNumber(totalAngleDeg)} degrés). Maximum ${formatNumber(program.maxTotalAngleDeg)} degrés.`,
    });
  }
  if (estimatedSeconds > program.maxProgramSeconds) {
    issues.push({
      message: `Ton programme dure trop longtemps (environ ${Math.round(estimatedSeconds)} s). Maximum ${program.maxProgramSeconds} s.`,
    });
  }

  // Une commande au-dela du domaine de temps n'est pas estimable : on signale.
  if (Number.isFinite(estimatedSeconds) === false) {
    issues.push({ message: 'On ne peut pas calculer la durée de ce programme.' });
  }

  return {
    valid: issues.length === 0,
    issues,
    summary: {
      stepCount: commands.length,
      totalDistanceCm,
      totalAngleDeg,
      estimatedSeconds: Math.round(estimatedSeconds * 10) / 10,
      capabilities: [...capabilities],
    },
  };
}

function formatNumber(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toFixed(1);
}

const KIND_LABELS: Record<string, string> = {
  move_forward: 'Avancer',
  move_backward: 'Reculer',
  turn_left: 'Tourner à gauche',
  turn_right: 'Tourner à droite',
  wait: 'Attendre',
  stand_up: 'Se mettre debout',
  sit_down: 'S’asseoir',
  stop: 'S’arrêter',
};

export function labelOf(kind: string): string {
  return KIND_LABELS[kind] ?? kind;
}