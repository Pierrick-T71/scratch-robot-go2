/**
 * Traduit l'espace de travail Blockly en `Program`.
 *
 * ## Principes
 *
 * - Aucun code généré, aucun `eval`. Le produit est une structure de données
 *   que le service validera puis exécutera.
 * - Aucune décision d'exécution ici : le compilateur ne peut pas savoir si
 *   « si la batterie est faible » est vrai. Il transmet, le service tranche.
 * - Un bloc inconnu est signalé, jamais ignoré en silence.
 * - Chaque instruction porte le numéro de ligne du bloc d'origine, pour que
 *   le service puisse situer un problème.
 *
 * ## Menus : une valeur refusée vaut un problème signalé
 *
 * Un menu ne peut contenir que des choix autorisés. Si la valeur enregistrée
 * n'y figure plus — programme importé, ancien format — on NE DEVINE PAS : on
 * signale, et on prend une valeur neutre. Un enfant ne doit pas voir le robot
 * partir avec une durée que personne n'a choisie.
 */

import * as Blockly from 'blockly/core';
import {
  BALANCE_BLOCK,
  CONDITIONS,
  CONDITION_CHOICES,
  DURATION_CHOICES,
  IF_BLOCK,
  IF_ELSE_BLOCK,
  MOVE_BACKWARD_BLOCK,
  MOVE_FORWARD_BLOCK,
  MOVE_LEFT_BLOCK,
  MOVE_RIGHT_BLOCK,
  REPEAT_BLOCK,
  REPEAT_CHOICES,
  SIT_DOWN_BLOCK,
  STAND_UP_BLOCK,
  START_BLOCK,
  STOP_MOVE_BLOCK,
  STOP_PROGRAM_BLOCK,
  TURN_CHOICES,
  TURN_LEFT_BLOCK,
  TURN_RIGHT_BLOCK,
  WAIT_BLOCK,
} from './blocks';
import type {
  ConditionKind,
  MoveDirection,
  Program,
  Statement,
  TurnDirection,
} from '../robot/program';

export interface CompileIssue {
  message: string;
  /** Numéro de ligne fautive, si connu. */
  line?: number;
  blockId?: string;
}

export interface CompileResult {
  program: Program;
  issues: CompileIssue[];
  hasStart: boolean;
  conditions: ConditionKind[];
}

const ALLOWED_DURATIONS = new Set(DURATION_CHOICES.map(([, value]) => value));
const ALLOWED_TURNS = new Set(TURN_CHOICES.map(([, value]) => value));
const ALLOWED_REPEATS = new Set(REPEAT_CHOICES.map(([, value]) => value));
const ALLOWED_CONDITIONS = new Set<string>(CONDITIONS);

/**
 * Lit un choix de menu, en refusant toute valeur non autorisée.
 *
 * C'est le garde-fou central du compilateur : un `FieldDropdown` accepte
 * n'importe quelle chaîne passée à `setValue`. Sans cette vérification, un
 * fichier de mission bricolé pourrait envoyer une durée de 10 000 s.
 */
function readChoice(
  block: Blockly.Block,
  fieldName: string,
  allowed: ReadonlySet<string>,
  fallback: string,
  label: string,
  issues: CompileIssue[],
): number {
  const raw = String(block.getFieldValue(fieldName) ?? '');
  if (!allowed.has(raw)) {
    issues.push({
      message: `Choix impossible pour « ${label} ».`,
      line: hashOf(block.id),
    });
    return Number(fallback);
  }
  return Number(raw);
}

/** Traduit une suite de blocs statements. */
function compileStatements(
  first: Blockly.Block | null,
  issues: CompileIssue[],
): Statement[] {
  const statements: Statement[] = [];
  const seen = new Set<string>();
  let current = first;

  while (current) {
    if (seen.has(current.id)) break; // garde-fou anti-cycle
    seen.add(current.id);
    const statement = compileStatement(current, issues);
    if (statement) statements.push(statement);
    current = current.getNextBlock();
  }
  return statements;
}

/** Traduit un bloc statement, ou `null` s'il n'en produit aucun. */
function compileStatement(block: Blockly.Block, issues: CompileIssue[]): Statement | null {
  const line = hashOf(block.id);

  switch (block.type) {
    case MOVE_FORWARD_BLOCK:
      return durationStatement(block, 'forward', line, issues);
    case MOVE_BACKWARD_BLOCK:
      return durationStatement(block, 'backward', line, issues);
    case MOVE_LEFT_BLOCK:
      return durationStatement(block, 'left', line, issues);
    case MOVE_RIGHT_BLOCK:
      return durationStatement(block, 'right', line, issues);

    case TURN_LEFT_BLOCK:
      return turnStatement(block, 'left', line, issues);
    case TURN_RIGHT_BLOCK:
      return turnStatement(block, 'right', line, issues);

    case STOP_MOVE_BLOCK:
      return { kind: 'stop_move', line };

    case STOP_PROGRAM_BLOCK:
      return { kind: 'stop_program', line };

    case WAIT_BLOCK:
      return {
        kind: 'wait',
        seconds: readChoice(block, 'SECONDS', ALLOWED_DURATIONS, '2', 'Attendre', issues),
        line,
      };

    case STAND_UP_BLOCK:
      return { kind: 'posture', posture: 'stand', line };
    case SIT_DOWN_BLOCK:
      return { kind: 'posture', posture: 'sit', line };
    case BALANCE_BLOCK:
      return { kind: 'posture', posture: 'balance', line };

    case REPEAT_BLOCK:
      return {
        kind: 'repeat',
        times: readChoice(block, 'COUNT', ALLOWED_REPEATS, '3', 'Répéter', issues),
        body: compileStatements(block.getInput('DO')?.connection?.targetBlock() ?? null, issues),
        line,
      };

    case IF_BLOCK:
    case IF_ELSE_BLOCK:
      return compileIf(block, line, issues);

    default:
      issues.push({
        message:
          'Un bloc n’est pas reconnu. Supprime-le ou remets-le dans la palette.',
        line,
      });
      return null;
  }
}

function compileIf(
  block: Blockly.Block,
  line: number,
  issues: CompileIssue[],
): Statement {
  const raw = String(block.getFieldValue('CONDITION') ?? '');
  const condition = (ALLOWED_CONDITIONS.has(raw) ? raw : 'posture_stand') as ConditionKind;
  if (!ALLOWED_CONDITIONS.has(raw)) {
    issues.push({ message: 'Cette condition n’est pas proposée.', line });
  }

  return {
    kind: 'if',
    condition,
    then: compileStatements(block.getInput('DO')?.connection?.targetBlock() ?? null, issues),
    otherwise:
      block.type === IF_ELSE_BLOCK
        ? compileStatements(block.getInput('ELSE')?.connection?.targetBlock() ?? null, issues)
        : undefined,
    line,
  };
}

function durationStatement(
  block: Blockly.Block,
  direction: MoveDirection,
  line: number,
  issues: CompileIssue[],
): Statement {
  return {
    kind: 'move',
    direction,
    seconds: readChoice(block, 'DURATION', ALLOWED_DURATIONS, '2', 'Déplacement', issues),
    line,
  };
}

function turnStatement(
  block: Blockly.Block,
  direction: TurnDirection,
  line: number,
  issues: CompileIssue[],
): Statement {
  return {
    kind: 'turn',
    direction,
    degrees: readChoice(block, 'ANGLE', ALLOWED_TURNS, '90', 'Rotation', issues),
    line,
  };
}

/**
 * Numéro de ligne stable, dérivé de l'identifiant du bloc.
 *
 * Blockly n'a pas de notion de ligne. On en fabrique une à partir de
 * l'identifiant, pour que le service puisse situer un problème sans que
 * l'interface ait à inventer un numéro de ligne.
 */
function hashOf(id: string): number {
  let hash = 0;
  for (let i = 0; i < id.length; i += 1) {
    hash = (hash * 31 + id.charCodeAt(i)) % 100000;
  }
  return hash;
}

/** Traduit l'ensemble de l'espace de travail. */
export function compileWorkspace(workspace: Blockly.Workspace): CompileResult {
  const issues: CompileIssue[] = [];
  const topBlocks = workspace.getTopBlocks(true);

  for (const block of topBlocks) {
    if (block.type === START_BLOCK) continue;
    if (block.getParent() === null) {
      issues.push({
        message:
          'Un bloc est seul, pas attaché au programme. Supprime-le ou accroche-le.',
        line: hashOf(block.id),
      });
    }
  }

  const startBlock = topBlocks.find((block) => block.type === START_BLOCK);
  if (!startBlock) {
    return {
      program: { statements: [] },
      issues: [
        { message: 'Il manque le bloc de départ « Quand je clique sur Démarrer ».' },
      ],
      hasStart: false,
      conditions: [],
    };
  }

  const statements = compileStatements(startBlock.getNextBlock(), issues);
  return {
    program: { statements },
    issues,
    hasStart: true,
    conditions: collectConditionsFrom(statements),
  };
}

function collectConditionsFrom(statements: readonly Statement[]): ConditionKind[] {
  const found: ConditionKind[] = [];
  const walk = (list: readonly Statement[]): void => {
    for (const statement of list) {
      if (statement.kind === 'if') {
        found.push(statement.condition);
        walk(statement.then);
        walk(statement.otherwise ?? []);
      } else if (statement.kind === 'repeat') {
        walk(statement.body);
      }
    }
  };
  walk(statements);
  return found;
}

/** Choix proposés, exposés pour les tests. */
export { DURATION_CHOICES, TURN_CHOICES, REPEAT_CHOICES, CONDITION_CHOICES };