/**
 * Etat applicatif central (runes Svelte 5).
 *
 * Contient la machine a etats de l'execution et la liaison avec le service.
 * Aucun acces bas niveau au robot : tout passe par `api` (voir lib/api).
 */
import { api, EventStream, LeaseKeeper, ServiceError, type RobotStatus, type ServiceMode } from '../api/client';
import type { RobotCommand } from '../robot/commands';
import { validateCommands, labelOf, type ValidationReport } from '../robot/validate';
import type { ProgramStep } from '../program/types';

export type ExecutionState =
  | 'idle'
  | 'checking'
  | 'ready'
  | 'starting'
  | 'running'
  | 'stopping'
  | 'done'
  | 'stopped'
  | 'error';

export interface AppNotice {
  tone: 'ok' | 'error' | 'warn';
  message: string;
}

/** Etat neutre avant toute connexion. */
const OFFLINE_STATUS: RobotStatus = {
  connected: false,
  mode: 'simulation',
  capabilities: [],
  executing: false,
  blockedReason: null,
  position: null,
  yawRad: null,
  batteryPercent: null,
};

class AppState {
  status = $state<RobotStatus>(OFFLINE_STATUS);
  execution = $state<ExecutionState>('idle');
  steps = $state<ProgramStep[]>([]);
  report = $state<ValidationReport | null>(null);
  notice = $state<AppNotice | null>(null);
  /** Action en attente de confirmation (mode reel). */
  pendingStart = $state<RobotCommand[] | null>(null);

  runId: string | null = null;

  #lease: LeaseKeeper | null = null;
  #stream: EventStream | null = null;

  get isBusy(): boolean {
    return this.execution === 'starting' || this.execution === 'running' || this.execution === 'stopping';
  }

  get modeLabel(): string {
    return this.status.mode === 'simulation' ? 'SIMULATION' : 'ROBOT RÉEL';
  }

  /** Le robot est-il dans un etat autorisant une mouvement physique ? */
  get realModeReady(): boolean {
    return this.status.mode === 'real' && this.status.connected;
  }

  #setNotice(tone: AppNotice['tone'], message: string): void {
    this.notice = { tone, message };
  }

  #setExecution(state: ExecutionState): void {
    this.execution = state;
  }

  /** Demarre la liaison d'evenements (une seule fois). */
  connect(): void {
    if (this.#stream) return;
    this.#stream = new EventStream((event) => this.#onEvent(event));
    this.#stream.connect();
    void this.refreshStatus();
  }

  disconnect(): void {
    this.#stream?.disconnect();
    this.#stream = null;
    this.#lease?.stop();
    this.#lease = null;
    void api.stop().catch(() => {
      /* le service s'arrete de lui-meme au terme du bail */
    });
  }

  async refreshStatus(): Promise<void> {
    try {
      this.status = await api.getStatus();
    } catch (error) {
      this.status = { ...OFFLINE_STATUS };
      if (error instanceof ServiceError && error.status === 0) {
        this.#setNotice(
          'warn',
          'Le service robot ne répond pas. L’application attend le service.',
        );
      }
    }
  }

  /**
   * Verifie le programme compile localement et met a jour l'affichage.
   * Ne declenche AUCUN mouvement.
   */
  check(commands: readonly RobotCommand[]): boolean {
    this.#setExecution('checking');
    const report = validateCommands(commands, this.status.capabilities);
    this.report = report;
    this.steps = commands.map((command, index) => ({
      index,
      label: describe(command),
      state: 'pending',
      outcome: null,
    }));

    if (report.valid) {
      this.#setExecution('ready');
      this.#setNotice('ok', 'Bravo ! Ton programme est prêt.');
    } else {
      this.#setExecution('error');
      this.#setNotice('error', report.issues[0]?.message ?? 'Ton programme a un problème.');
    }
    return report.valid;
  }

  /** Demande de lancement. En mode reel, passe par une confirmation adulte. */
  requestStart(commands: readonly RobotCommand[]): void {
    if (this.isBusy) {
      this.#setNotice('warn', 'Un programme est déjà en cours.');
      return;
    }
    if (this.status.mode === 'real' && !this.status.connected) {
      this.#setNotice('error', 'Le robot n’est pas connecté. Demande de l’aide à l’adulte.');
      return;
    }
    if (this.status.mode === 'real') {
      // Passage par la confirmation adulte : aucune exception.
      this.pendingStart = [...commands];
      return;
    }
    void this.#start(commands);
  }

  confirmPendingStart(): void {
    const commands = this.pendingStart;
    this.pendingStart = null;
    if (commands) void this.#start(commands);
  }

  cancelPendingStart(): void {
    this.pendingStart = null;
  }

  async #start(commands: readonly RobotCommand[]): Promise<void> {
    this.#setExecution('starting');
    this.steps = commands.map((command, index) => ({
      index,
      label: describe(command),
      state: 'pending',
      outcome: null,
    }));

    try {
      const response = await api.start({ commands: [...commands], adultAuthorised: true });
      this.runId = response.runId;
      this.#lease = new LeaseKeeper(response.runId);
      this.#lease.start();
      this.#setExecution('running');
      this.#setNotice('ok', 'C’est parti !');
    } catch (error) {
      this.#setExecution('error');
      const message =
        error instanceof ServiceError ? error.message : 'Le programme n’a pas pu démarrer.';
      this.#setNotice('error', message);
    }
  }

  /** Arret demande. Le service reste responsable de l'arret physique. */
  async requestStop(): Promise<void> {
    if (!this.isBusy) return;
    this.#setExecution('stopping');
    this.#setNotice('warn', 'Arrêt demandé…');
    try {
      await api.stop();
    } catch {
      // Le chien de garde du service reste le garant de l'arrêt.
      this.#setNotice(
        'error',
        'Le service ne répond plus. Le robot doit être arrêté avec la télécommande.',
      );
    } finally {
      this.#lease?.stop();
      this.#lease = null;
    }
  }

  async setMode(mode: ServiceMode, adultAuthorised: boolean): Promise<void> {
    try {
      this.status = await api.setMode(mode, adultAuthorised);
      this.#setNotice(
        'ok',
        mode === 'simulation'
          ? 'Mode simulation activé. Aucun mouvement réel.'
          : 'Mode robot réel activé. Vérifie que la zone est dégagée.',
      );
      this.check(this.currentCommands);
    } catch (error) {
      this.#setNotice(
        'error',
        error instanceof ServiceError ? error.message : 'Changement de mode refusé.',
      );
      await this.refreshStatus();
    }
  }

  /** Dernier programme compile, pour revalider apres un changement de mode. */
  currentCommands: RobotCommand[] = [];

  setCommands(commands: readonly RobotCommand[]): void {
    this.currentCommands = [...commands];
  }

  #onEvent(event: import('../api/client').ExecutionEvent): void {
    switch (event.type) {
      case 'status':
        this.status = event.status;
        break;
      case 'step_started':
        this.#updateStep(event.index, { state: 'running' });
        break;
      case 'step_completed':
        this.#updateStep(event.index, { state: 'done' });
        break;
      case 'step_finished':
        // « mesuré » n'est affiché QUE si une mesure a réellement été
        // retournée. Une posture, par exemple, est envoyée sans confirmation
        // par le SDK : la dire « mesurée » serait un mensonge.
        this.#updateStep(event.index, {
          state: event.outcome === 'exact' ? 'done' : 'stopped',
          outcome: describeOutcome(event.outcome, event.measured),
        });
        break;
      case 'execution_finished':
        this.#onFinished(event.reason);
        break;
      case 'error':
        this.#setNotice('error', event.message);
        this.#setExecution('error');
        break;
    }
  }

  #updateStep(index: number, patch: Partial<ProgramStep>): void {
    this.steps = this.steps.map((step) =>
      step.index === index ? { ...step, ...patch } : step,
    );
  }

  #onFinished(reason: 'completed' | 'stopped' | 'error' | 'safety'): void {
    this.#lease?.stop();
    this.#lease = null;
    this.runId = null;

    switch (reason) {
      case 'completed':
        this.#setExecution('done');
        this.#setNotice('ok', 'Terminé ! Le programme s’est bien déroulé.');
        break;
      case 'stopped':
        this.#setExecution('stopped');
        this.#setNotice(
          'warn',
          'Le programme a été arrêté. Vérifie que le robot est immobile avant de continuer.',
        );
        break;
      case 'safety':
        this.#setExecution('stopped');
        this.#setNotice(
          'error',
          'Sécurité : le service a arrêté le robot. Demande de l’aide à l’adulte.',
        );
        break;
      case 'error':
        this.#setExecution('error');
        this.#setNotice('error', 'Le programme s’est interrompu. Demande de l’aide à l’adulte.');
        break;
    }
  }
}

/** Libelle en francais d'une instruction. */
export function describe(command: RobotCommand): string {
  switch (command.kind) {
    case 'move_forward':
      return `Avancer de ${command.distanceCm} cm`;
    case 'move_backward':
      return `Reculer de ${command.distanceCm} cm`;
    case 'turn_left':
      return `Tourner à gauche de ${command.angleDeg}°`;
    case 'turn_right':
      return `Tourner à droite de ${command.angleDeg}°`;
    case 'wait':
      return `Attendre ${command.seconds} s`;
    case 'stand_up':
      return 'Se mettre debout';
    case 'sit_down':
      return 'S’asseoir';
    case 'stop':
      return 'S’arrêter';
    default:
      return labelOf((command as { kind: string }).kind);
  }
}

type Measured = { distanceCm?: number; angleDeg?: number } | null;

/**
 * Libellé de fin d'étape, honnête sur ce qui est réellement connu.
 *
 * `exact` + mesure       -> « mesuré » + la valeur
 * `exact` sans mesure    -> « terminé » (consigne envoyée, sans retour du SDK)
 * `timeout`              -> « temps écoulé » + ce qui a été mesuré
 * `stopped`              -> arrêté sur demande
 */
export function describeOutcome(
  outcome: string,
  measured: Measured,
): string {
  switch (outcome) {
    case 'exact':
      return measured ? `mesuré · ${formatMeasured(measured)}` : 'terminé';
    case 'timeout':
      return `temps écoulé (${formatMeasured(measured)})`;
    case 'stopped':
      return 'arrêté';
    case 'failed':
      return 'échec';
    default:
      return outcome;
  }
}

function formatMeasured(measured: Measured): string {
  if (!measured) return 'non mesuré';
  if (measured.distanceCm !== undefined) return `${measured.distanceCm} cm`;
  if (measured.angleDeg !== undefined) return `${measured.angleDeg}°`;
  return 'non mesuré';
}

export const app = new AppState();