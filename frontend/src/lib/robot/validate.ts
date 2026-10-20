/**
 * Validation d'un programme avant envoi au service.
 *
 * Cette validation est un **confort pour l'enfant** (retour immédiat, message
 * clair). Elle ne remplace PAS la validation du service, qui reste la seule
 * opposable : un client modifié reçoit exactement le même refus.
 *
 * Elle porte sur ce qui est vérifiable SANS exécuter : durées, nombre de
 * répétitions, imbrication, durée totale.
 *
 * Elle NE DEVINE JAMAIS une condition : « si la batterie est faible » ne peut
 * pas être évaluée ici. Le service est seul juge.
 */
import type { Program, Statement } from './program';
import { countSteps, estimateDuration } from './program';
import { LOW_BATTERY_PERCENT, MAX_DURATION_S } from './bounds';

export interface ValidationIssue {
  message: string;
  line?: number;
}

export interface ProgramSummary {
  stepCount: number;
  /** Durée du pire cas, en secondes. */
  estimatedSeconds: number;
}

export interface ValidationReport {
  valid: boolean;
  issues: ValidationIssue[];
  summary: ProgramSummary;
}

/** Durées réellement proposées dans les menus. */
const ALLOWED_SECONDS = new Set([1, 2, 3, 5]);
/** Angles réellement proposés dans les menus. */
const ALLOWED_DEGREES = new Set([45, 90, 180]);
/** Nombres de répétitions réellement proposés dans les menus. */
const ALLOWED_TIMES = new Set([2, 3, 5, 10]);

/** Conditions dont l'état peut changer : durée non bornable. */
const ALWAYS_CHANGES = new Set(['posture_stand', 'battery_low']);

/** Nombre maximal de répétitions imbriquées. */
const MAX_DEPTH = 3;
/** Nombre maximal d'instructions, répétitions développées. */
const MAX_STEPS = 500;
/** Durée totale maximale, en secondes. */
const MAX_SECONDS = 120;

function describe(condition: string): string {
  switch (condition) {
    case 'posture_stand':
      return 'le robot est debout';
    case 'battery_low':
      return 'la batterie est faible';
    default:
      return condition;
  }
}

function checkStatements(
  statements: readonly Statement[],
  issues: ValidationIssue[],
  depth: number,
): void {
  if (depth > MAX_DEPTH) {
    issues.push({
      message: `Les répétitions sont imbriquées trop profondément (maximum ${MAX_DEPTH}).`,
    });
    return;
  }

  for (const statement of statements) {
    const line = statement.line;

    switch (statement.kind) {
      case 'move':
        if (!ALLOWED_SECONDS.has(statement.seconds)) {
          issues.push({
            message: 'Ce déplacement propose une durée impossible.',
            line,
          });
        }
        break;

      case 'wait':
        if (!ALLOWED_SECONDS.has(statement.seconds)) {
          issues.push({ message: 'Cette attente propose une durée impossible.', line });
        }
        break;

      case 'turn':
        if (!ALLOWED_DEGREES.has(statement.degrees)) {
          issues.push({
            message: 'Cette rotation propose un angle impossible.',
            line,
          });
        }
        break;

      case 'repeat':
        if (!ALLOWED_TIMES.has(statement.times)) {
          issues.push({
            message: 'Ce bloc répète un nombre de fois impossible.',
            line,
          });
        }
        checkStatements(statement.body, issues, depth + 1);
        break;

      case 'if':
        // La condition n'est PAS évaluée ici. On vérifie seulement qu'elle
        // existe : c'est le service qui dira si elle est vraie.
        if (!ALWAYS_CHANGES.has(statement.condition)) {
          issues.push({ message: 'Cette condition n’est pas proposée.', line });
        }
        checkStatements(statement.then, issues, depth + 1);
        checkStatements(statement.otherwise ?? [], issues, depth + 1);
        break;

      default:
        break;
    }
  }
}

/** Valide un programme complet. */
export function validateProgram(program: Program): ValidationReport {
  const issues: ValidationIssue[] = [];
  const statements = program.statements;

  if (statements.length === 0) {
    issues.push({
      message: 'Ton programme ne fait rien. Accroche un bloc sous le bloc de départ.',
    });
  }

  checkStatements(statements, issues, 0);

  const stepCount = countSteps(statements);
  const seconds = estimateDuration(statements);

  if (stepCount > MAX_STEPS) {
    issues.push({
      message: `Ton programme est trop long (${stepCount} pas). Maximum ${MAX_STEPS}.`,
    });
  }
  if (seconds > MAX_SECONDS) {
    issues.push({
      message: `Ton programme dure trop longtemps (environ ${Math.round(
        seconds,
      )} s). Maximum ${MAX_SECONDS} s.`,
    });
  }

  return {
    valid: issues.length === 0,
    issues,
    summary: {
      stepCount,
      estimatedSeconds: Math.round(seconds * 10) / 10,
    },
  };
}

export { LOW_BATTERY_PERCENT, MAX_DURATION_S, describe as describeCondition };