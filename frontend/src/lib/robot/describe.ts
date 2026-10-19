/**
 * Traduction des instructions en phrases françaises.
 *
 * Phrases courtes, mots simples. Aucun terme technique dans ce qui sera lu
 * par un enfant : pas de « variable », « expression », « API », ni
 * « vitesse linéaire ». La vitesse est une décision du service, pas un mot
 * que l'enfant a besoin de rencontrer.
 */
import type { Statement } from './program';

const MOVE_LABELS: Record<string, string> = {
  forward: 'Avancer',
  backward: 'Reculer',
  left: 'Aller à gauche',
  right: 'Aller à droite',
};

const TURN_LABELS: Record<string, string> = {
  left: 'Tourner à gauche',
  right: 'Tourner à droite',
};

const POSTURE_LABELS: Record<string, string> = {
  stand: 'Se mettre debout',
  sit: 'S’asseoir',
  balance: 'Se stabiliser',
};

const CONDITION_LABELS: Record<string, string> = {
  posture_stand: 'le robot est debout',
  battery_low: 'la batterie est faible',
};

/** Formulation d'une durée, accordée en nombre. */
function seconds(value: number): string {
  return value === 1 ? '1 seconde' : `${value} secondes`;
}

/** Phrase décrivant une instruction, pour le panneau d'étapes. */
export function describeStatement(statement: Statement): string {
  switch (statement.kind) {
    case 'move':
      return `${MOVE_LABELS[statement.direction] ?? statement.direction} pendant ${seconds(
        statement.seconds,
      )}`;
    case 'turn':
      return `${TURN_LABELS[statement.direction] ?? statement.direction} de ${statement.degrees}°`;
    case 'wait':
      return `Attendre ${seconds(statement.seconds)}`;
    case 'posture':
      return POSTURE_LABELS[statement.posture] ?? statement.posture;
    case 'stop_move':
      return 'Arrêter le robot';
    case 'stop_program':
      return 'Arrêter le programme';
    case 'repeat':
      return `Répéter ${statement.times} fois`;
    case 'if':
      return `Si ${CONDITION_LABELS[statement.condition] ?? statement.condition}`;
  }
}

/** Formulation d'une condition, pour les messages. */
export function describeCondition(condition: string): string {
  return CONDITION_LABELS[condition] ?? condition;
}