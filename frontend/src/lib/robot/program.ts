/**
 * Programme GO2 Scratch : structure simple, sans variables ni expressions.
 *
 * ## Pourquoi ce modèle est aussi maigre
 *
 * L'enfant ne crée pas de variable et n'écrit pas de formule. Toutes les
 * valeurs sont des **choix** menus, résolus à la compilation. Il ne reste donc
 * que deux formes d'instruction :
 *
 *  - une **action** : « avancer pendant 2 secondes » ;
 *  - une **structure** : « répéter 3 fois », « si … alors ».
 *
 * Pas d'`Expr`, pas d'arbre d'opérateurs, pas de capteur libre. C'est
 * volontaire : chaque suppression supprime un cas où l'interface pouvait
 * afficher un trou vide ou une valeur inventée.
 *
 * ## Le service reste seul juge
 *
 * Ce modèle est une *demande*. Le service la valide entièrement, borne les
 * durées, et décide seul si une condition est vraie au moment de l'exécuter.
 */

/** Direction d'un déplacement. */
export type MoveDirection = 'forward' | 'backward' | 'left' | 'right';
export type TurnDirection = 'left' | 'right';

/** Postures exposées aux enfants, toutes vérifiées dans le SDK lu. */
export type Posture = 'stand' | 'sit' | 'balance' | 'lie_down';

/** Gestes du corps exposés aux enfants. */
export type Gesture = 'heart' | 'jump' | 'salute' | 'stretch';

/**
 * Conditions réellement implémentées.
 *
 * ⚠️ Toute condition ajoutée ici doit être VRAIE à l'exécution, mesurée par le
 * service. `obstacle` en est volontairement absent : le SDK officiel lu
 * n'expose aucune mesure de distance.
 */
export type ConditionKind = 'posture_stand' | 'battery_low';

export interface MoveStatement {
  kind: 'move';
  direction: MoveDirection;
  /** Durée demandée, en secondes. Bornée par le service. */
  seconds: number;
  line: number;
}

export interface TurnStatement {
  kind: 'turn';
  direction: TurnDirection;
  /**
   * Angle demandé, en degrés.
   *
   * Le cap du robot est une donnée MESURÉE (`SportModeState_`), donc un angle
   * est vérifiable — contrairement à une distance, qui ne l'est pas.
   */
  degrees: number;
  line: number;
}

export interface WaitStatement {
  kind: 'wait';
  seconds: number;
  line: number;
}

export interface PostureStatement {
  kind: 'posture';
  posture: Posture;
  line: number;
}

/**
 * Un geste du corps, sans acrobatie.
 *
 * Aujourd'hui : le cœur, le saut, saluer et s'étirer, tous des commandes
 * officielles du SDK. Le service refuse tout geste qu'il ne sait pas exécuter.
 */
export interface GestureStatement {
  kind: 'gesture';
  gesture: Gesture;
  line: number;
}

export interface StopMoveStatement {
  kind: 'stop_move';
  line: number;
}

export interface StopProgramStatement {
  kind: 'stop_program';
  line: number;
}

export interface RepeatStatement {
  kind: 'repeat';
  times: number;
  body: Statement[];
  line: number;
}

export interface IfStatement {
  kind: 'if';
  condition: ConditionKind;
  then: Statement[];
  otherwise?: Statement[];
  line: number;
}

export type Statement =
  | MoveStatement
  | TurnStatement
  | WaitStatement
  | PostureStatement
  | GestureStatement
  | StopMoveStatement
  | StopProgramStatement
  | RepeatStatement
  | IfStatement;

/** Programme complet, prêt à être validé puis exécuté. */
export interface Program {
  statements: Statement[];
}

/** Instructions qui ne pilotent aucun organe. */
export const CONTROL_KINDS: ReadonlySet<string> = new Set(['repeat', 'if', 'stop_program']);

/** `true` si l'instruction atteint le robot. */
export function isPhysicalStatement(statement: Statement): boolean {
  return !CONTROL_KINDS.has(statement.kind);
}

/** Nombre d'instructions, répétitions développées. */
export function countSteps(statements: readonly Statement[]): number {
  let total = 0;
  for (const statement of statements) {
    if (statement.kind === 'repeat') {
      total += statement.times * Math.max(1, countSteps(statement.body));
    } else if (statement.kind === 'if') {
      total += 1 + countSteps(statement.then) + countSteps(statement.otherwise ?? []);
    } else {
      total += 1;
    }
  }
  return total;
}

/**
 * Durée maximale possible, en secondes.
 *
 * Pour une condition, c'est la plus longue des deux branches : on ne peut pas
 * savoir à l'avance laquelle sera prise, donc on retient la plus longue.
 */
export function estimateDuration(statements: readonly Statement[]): number {
  let total = 0;
  for (const statement of statements) {
    switch (statement.kind) {
      case 'move':
      case 'wait':
        total += statement.seconds;
        break;
      case 'turn':
        // Angulaire : 0,5 rad/s, soit environ 28,6°/s.
        total += Math.abs(statement.degrees) / 28.6;
        break;
      case 'repeat':
        total += statement.times * estimateDuration(statement.body);
        break;
      case 'if':
        // Pire cas : la plus LONGUE des deux branches.
        // Prendre « alors » par défaut refuserait à tort un programme dont le
        // « sinon » est le plus long — et le service, lui, peut le prendre.
        total += Math.max(
          estimateDuration(statement.then),
          estimateDuration(statement.otherwise ?? []),
        );
        break;
      default:
        break;
    }
  }
  return total;
}

/**
 * Aplatit un programme pour l'AFFICHAGE des étapes, répétitions développées.
 *
 * ⚠️ Usage strictement cosmétique. Une condition n'est pas dépliable : elle
 * est conservée telle quel et compte comme UNE étape, ce qui évite d'annoncer
 * à l'enfant des mouvements qui n'auront peut-être pas lieu.
 */
export function flattenForDisplay(
  statements: readonly Statement[],
  limit = 200,
): Statement[] {
  const out: Statement[] = [];
  const walk = (list: readonly Statement[]): void => {
    for (const statement of list) {
      if (out.length >= limit) return;
      if (statement.kind === 'repeat') {
        for (let i = 0; i < statement.times && out.length < limit; i += 1) {
          walk(statement.body);
        }
      } else {
        out.push(statement);
      }
    }
  };
  walk(statements);
  return out;
}

/** Messages émis par le programme, dans l'ordre d'apparition. */
export function collectConditions(statements: readonly Statement[]): ConditionKind[] {
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