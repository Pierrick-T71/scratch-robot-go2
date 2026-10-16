/**
 * Compilateur : espace de travail Blockly -> instruction GO2 interne.
 *
 * Aucune generation de code. On produit une structure de donnees pure
 * (`RobotCommand`) qui sera validee puis envoyee au service. Le service
 * revalide integralement de son cote : cette validation ici ne sert qu'au
 * retour immediat a l'enfant.
 */
import type { Blockly } from './workspace';
import {
  START_BLOCK,
  WAIT_BLOCK,
  FORWARD_BLOCK,
  BACKWARD_BLOCK,
  TURN_LEFT_BLOCK,
  TURN_RIGHT_BLOCK,
  STOP_BLOCK,
  STAND_UP_BLOCK,
  SIT_DOWN_BLOCK,
  REPEAT_BLOCK,
} from './blocks';
import type { RobotCommand } from '../robot/commands';

export interface CompileIssue {
  /** Message simple, en francais, destine a l'enfant. */
  message: string;
  /** Id du bloc fautif si connu. */
  blockId?: string;
}

export interface CompileResult {
  commands: RobotCommand[];
  issues: CompileIssue[];
  /** Vrai si le programme contient au moins un bloc de depart. */
  hasStart: boolean;
}

/**
 * Lit la valeur numerique d'une entree de bloc.
 *
 * L'entree est un bloc-valeur (ombre `math_number` par defaut, ou un autre
 * bloc imbrique). On lit le premier champ du bloc connecte.
 */
function readNumericValue(
  block: Blockly.Block,
  fieldName: string,
  issues: CompileIssue[],
): number | null {
  const input = block.getInput(fieldName);
  const source = input?.connection?.targetBlock();

  if (!source) {
    issues.push({ message: 'Il manque un nombre dans un bloc.', blockId: block.id });
    return null;
  }

  let raw: unknown = null;
  for (const field of source.getFields()) {
    if (!field.name) continue;
    raw = source.getFieldValue(field.name);
    if (raw !== null && raw !== undefined && raw !== '') break;
    raw = null;
  }

  if (raw === null || raw === undefined || raw === '') {
    issues.push({ message: 'Il manque un nombre dans un bloc.', blockId: block.id });
    return null;
  }
  const value = Number(raw);
  if (!Number.isFinite(value)) {
    issues.push({ message: 'Ce nombre n’est pas compris.', blockId: block.id });
    return null;
  }
  return value;
}

/** Empilement de blocs pour parcourir une chaine `nextConnection`. */
function chainOf(first: Blockly.Block | null): Blockly.Block[] {
  const chain: Blockly.Block[] = [];
  let current = first;
  const seen = new Set<string>();
  while (current) {
    if (seen.has(current.id)) break; // garde-fou contre un cycle
    seen.add(current.id);
    chain.push(current);
    current = current.getNextBlock();
  }
  return chain;
}

/** Compile une chaine de blocs sequentiels. */
function compileSequence(
  first: Blockly.Block | null,
  issues: CompileIssue[],
  depth: number,
): RobotCommand[] {
  const commands: RobotCommand[] = [];

  for (const block of chainOf(first)) {
    switch (block.type) {
      case WAIT_BLOCK: {
        const seconds = readNumericValue(block, 'DURATION', issues);
        if (seconds !== null) commands.push({ kind: 'wait', seconds });
        break;
      }
      case FORWARD_BLOCK: {
        const distanceCm = readNumericValue(block, 'DISTANCE', issues);
        if (distanceCm !== null) commands.push({ kind: 'move_forward', distanceCm });
        break;
      }
      case BACKWARD_BLOCK: {
        const distanceCm = readNumericValue(block, 'DISTANCE', issues);
        if (distanceCm !== null) commands.push({ kind: 'move_backward', distanceCm });
        break;
      }
      case TURN_LEFT_BLOCK: {
        const angleDeg = readNumericValue(block, 'ANGLE', issues);
        if (angleDeg !== null) commands.push({ kind: 'turn_left', angleDeg });
        break;
      }
      case TURN_RIGHT_BLOCK: {
        const angleDeg = readNumericValue(block, 'ANGLE', issues);
        if (angleDeg !== null) commands.push({ kind: 'turn_right', angleDeg });
        break;
      }
      case STOP_BLOCK:
        commands.push({ kind: 'stop' });
        break;
      case STAND_UP_BLOCK:
        commands.push({ kind: 'stand_up' });
        break;
      case SIT_DOWN_BLOCK:
        commands.push({ kind: 'sit_down' });
        break;
      case REPEAT_BLOCK: {
        const count = readNumericValue(block, 'COUNT', issues);
        const body = compileSequence(block.getInputTargetBlock('DO'), issues, depth + 1);
        if (count === null) break;
        if (count < 1 || !Number.isInteger(count)) {
          issues.push({
            message: 'Le nombre de répétitions doit être un nombre entier plus grand que 0.',
            blockId: block.id,
          });
          break;
        }
        // Le corps est aplati ici : le moteur gere l'aplatissement, ce qui evite
        // toute recursion illimitee et rend les cumuls triviaux a controler.
        for (let i = 0; i < count; i += 1) commands.push(...body);
        break;
      }
      default:
        // Bloc inconnu (corruption, autre categorie) : signale, n'execute pas.
        issues.push({
          message: 'Un bloc n’est pas reconnu. Supprime-le ou remets-le dans la palette.',
          blockId: block.id,
        });
        break;
    }
  }
  return commands;
}

/**
 * Compile l'ensemble de l'espace de travail.
 *
 * Regle : un programme DOIT contenir exactement un bloc `go2_start`, et
 * aucun bloc ne doit etre execute avant lui.
 */
export function compileWorkspace(blockly: typeof import('./workspace').Blockly): CompileResult {
  const issues: CompileIssue[] = [];
  const topBlocks = blockly.getMainWorkspace().getTopBlocks(true);

  const startBlock = topBlocks.find((b) => b.type === START_BLOCK);

  // Reperage des blocs flottants qui ne sont pas rattaches au programme.
  for (const block of topBlocks) {
    if (block.type === START_BLOCK) continue;
    if (!block.isEnabled()) continue;
    if (block.getParent() === null) {
      issues.push({
        message: 'Un bloc est seul, pas attaché au programme. Supprime-le ou accroche-le.',
        blockId: block.id,
      });
    }
  }

  if (!startBlock) {
    return {
      commands: [],
      issues: [{ message: 'Il manque le bloc de départ « Quand je clique sur Démarrer ».' }],
      hasStart: false,
    };
  }

  const commands = compileSequence(startBlock.getNextBlock(), issues, 0);
  return { commands, issues, hasStart: true };
}