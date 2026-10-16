/** Types de l'affichage de la progression d'un programme. */

export type StepState = 'pending' | 'running' | 'done' | 'stopped';

export interface ProgramStep {
  index: number;
  label: string;
  state: StepState;
  /** Precision sur la fin d'etape : 'mesuré' ou motif de l'ecart. */
  outcome: string | null;
}