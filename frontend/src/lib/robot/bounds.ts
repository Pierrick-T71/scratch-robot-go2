/**
 * Bornes partagées entre l'interface et la validation.
 *
 * Ce module est volontairement minuscule et sans dépendance : il peut être
 * importé par la validation enfant sans embarquer Blockly. C'est ce qui
 * permet à « Go2 Play » d'être un écran léger, même si l'ancien éditeur
 * Blockly reste dans le dépôt.
 */
import { SAFETY } from './limits';

/** En dessous de ce pourcentage, la batterie est considérée faible. */
export const LOW_BATTERY_PERCENT = 30;

/** Durée maximale d'attente acceptée (s), issue des limites partagées. */
export const MAX_DURATION_S = SAFETY.timing.maxWaitSeconds;
