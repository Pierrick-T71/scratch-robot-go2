/**
 * Etat applicatif central (runes Svelte 5).
 *
 * Contient la machine a etats de l'execution et la liaison avec le service.
 * Aucun acces bas niveau au robot : tout passe par `api` (voir lib/api).
 */
import {
  api,
  EventStream,
  LeaseKeeper,
  ServiceError,
  type ManualDirection,
  type ManualMoveResult,
  type RobotStatus,
  type ServiceMode,
} from '../api/client';
import { validateProgram, type ValidationReport } from '../robot/validate';
import type { SettingsPayload, SettingsValues } from '../robot/settings';
import { describeStatement } from '../robot/describe';
import { flattenForDisplay, type Program, type Statement } from '../robot/program';
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

/** Message bloquant affiché dans une fenêtre au centre de l'écran. */
export interface BlockedNotice {
  title: string;
  message: string;
  /** `blocked` : le pas n'a pas commencé. `stopped` : arrêt pendant le pas. */
  kind: 'blocked' | 'stopped';
}

/** Etat neutre avant toute connexion. */
const OFFLINE_STATUS: RobotStatus = {
  connected: false,
  mode: 'simulation',
  capabilities: [],
  executing: false,
  manualActive: false,
  blockedReason: null,
  safetyReason: null,
  recoveryReason: null,
  position: null,
  yawRad: null,
  batteryPercent: null,
  posture: null,
  settingsRevision: 0,
  obstacleSafetyEnabled: true,
  obstacleSafetyAvailable: false,
  standby: false,
  standbyTransition: null,
  manualSource: null,
  manualCrouchActive: false,
  autonomousActive: false,
  autonomousStopReason: null,
  lanIp: '172.16.13.41',
};

class AppState {
  status = $state<RobotStatus>(OFFLINE_STATUS);
  execution = $state<ExecutionState>('idle');
  steps = $state<ProgramStep[]>([]);
  report = $state<ValidationReport | null>(null);
  notice = $state<AppNotice | null>(null);
  /** Fenêtre centrale quand une action est refusée faute de place. */
  blockedNotice = $state<BlockedNotice | null>(null);
  /** Programme en attente de confirmation (mode reel). */
  pendingStart = $state<Program | null>(null);
  /** Reglages en vigueur, fournis par le service (bornes incluses). */
  settings = $state<SettingsPayload | null>(null);

  runId: string | null = null;
  /** Revision des reglages au moment de la derniere verification. */
  #validatedRevision = 0;

  #lease: LeaseKeeper | null = null;
  #stream: EventStream | null = null;

  get isBusy(): boolean {
    return (
      this.execution === 'starting' ||
      this.execution === 'running' ||
      this.execution === 'stopping' ||
      this.status.standby === true ||
      Boolean(this.status.standbyTransition) ||
      Boolean(this.status.autonomousActive)
    );
  }

  /**
   * Met a jour la liste des etapes sans toucher au verdict.
   *
   * Appele a chaque modification du programme. Sans cela, la liste affichait
   * des valeurs perimees apres un changement de nombre, alors que le robot
   * executerait, lui, le nouveau programme : l'ecran mentirait.
   */
  syncSteps(statements: readonly Statement[]): void {
    // Tant qu'aucune verification n'a eu lieu, la liste n'a pas de sens a
    // afficher : on laisse le panneau vide et l'enfant invite a verifier.
    if (this.report === null) return;
    const flat = flattenForDisplay(statements);
    this.steps = flat.map((statement, index) => {
      const previous = this.steps.find((s) => s.index === index);
      return {
        index,
        label: describeStatement(statement),
        // Une etape en cours d'execution garde son etatuel.
        state: previous?.state === 'running' ? 'running' : 'pending',
        outcome: previous?.state === 'running' ? previous.outcome : null,
      } satisfies ProgramStep;
    });
  }

  /**
   * Vrai si les reglages ont change depuis la derniere verification :
   * le rapport affiche n'est alors plus valable.
   */
  get reportIsStale(): boolean {
    return this.report !== null && this.status.settingsRevision !== this.#validatedRevision;
  }

  async refreshSettings(): Promise<void> {
    try {
      this.settings = await api.getSettings();
    } catch {
      // Le service ne repond pas : on garde les valeurs precedentes.
      this.settings = null;
    }
  }

  /**
   * Applique des reglages. Cote service, donc reellement contraignants :
   * l'interface n'est qu'un support d'affichage.
   */
  async saveSettings(values: SettingsValues): Promise<boolean> {
    try {
      const payload = await api.saveSettings(values);
      this.settings = payload;
      await this.refreshStatus();
      // Le rapport précédent n'a plus de valeur : on le force à recalculer.
      this.#validatedRevision = -1;
      this.check(this.currentProgram);
      this.#setNotice('ok', 'Réglages appliqués.');
      return true;
    } catch (error) {
      this.#setNotice(
        'error',
        error instanceof ServiceError ? error.message : 'Réglages refusés par le service.',
      );
      return false;
    }
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
    void api.stopManual().catch(() => {
      /* le bail manuel expirera de lui-même côté service */
    });
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
  check(program: Program): boolean {
    this.#setExecution('checking');

    const report = validateProgram(program);
    this.report = report;
    this.steps = flattenForDisplay(program.statements).map((statement, index) => ({
      index,
      label: describeStatement(statement),
      state: 'pending',
      outcome: null,
    }));

    this.#validatedRevision = this.status.settingsRevision;

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
  requestStart(program: Program): void {
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
      this.pendingStart = program;
      return;
    }
    void this.#start(program);
  }

  confirmPendingStart(): void {
    const program = this.pendingStart;
    this.pendingStart = null;
    if (program) void this.#start(program);
  }

  cancelPendingStart(): void {
    this.pendingStart = null;
  }

  async #start(program: Program): Promise<void> {
    this.#setExecution('starting');
    this.blockedNotice = null;
    this.status = {
      ...this.status,
      position: { x: 0, y: 0, z: 0 },
      yawRad: 0,
      posture: 'stand',
    };
    this.steps = flattenForDisplay(program.statements).map((statement, index) => ({
      index,
      label: describeStatement(statement),
      state: 'pending',
      outcome: null,
    }));

    try {
      const response = await api.start({
        program,
        adult_authorised: true,
      });

      // ⚠️ Le programme peut être DÉJÀ terminé quand la réponse arrive.
      // En simulation, un programme d'une seule posture (« s'asseoir »)
      // finit en quelques millisecondes : les événements de fin passent
      // AVANT la réponse HTTP. Repasser en « running » ici rouvrirait une
      // exécution morte : l'interface resterait bloquée sur un programme
      // arrêté, bouton « Lancer » désactivé pour toujours.
      if (this.execution !== 'starting') {
        this.runId = null;
        return;
      }

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
      // Si aucun événement de fin ne suit (le programme était déjà arrêté,
      // ou le service n'en a rien à dire), on ne reste pas bloqué sur
      // « arrêt en cours » : l'arrêt a bien été demandé.
      if (this.execution === 'stopping') {
        this.#setExecution('stopped');
        this.#setNotice(
          'warn',
          'Le programme a été arrêté. Vérifie que le robot est immobile avant de continuer.',
        );
      }
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

  /** Ouvre le mode manuel. Le service garde la main sur la vitesse. */
  async startManual(): Promise<boolean> {
    if (this.isBusy) return false;
    try {
      await api.startManual(true);
      return true;
    } catch (error) {
      this.#setNotice(
        'error',
        error instanceof ServiceError
          ? error.message
          : 'Le mode manuel n’a pas pu démarrer.',
      );
      return false;
    }
  }

  /** Presse ou relâche une touche. `null` arrête immédiatement. */
  async moveManual(
    direction: ManualDirection | null,
    seq: number,
    source: 'keyboard' | 'mobile' = 'keyboard',
  ): Promise<ManualMoveResult> {
    try {
      return await api.moveManual(direction, seq, source);
    } catch (error) {
      return {
        active: false,
        blocked: direction !== null,
        message:
          error instanceof ServiceError
            ? error.message
            : 'Le robot ne répond pas au pilotage manuel.',
      };
    }
  }

  /** Ferme le mode manuel et immobilise le robot. */
  async stopManual(): Promise<void> {
    try {
      await api.stopManual();
    } catch {
      /* le bail manuel expirera de lui-même côté service */
    }
  }

  /** Déclenche un saut en mode manuel (barre espace ou bouton mobile). */
  async jumpManual(
    source: 'keyboard' | 'mobile' = 'keyboard',
  ): Promise<{ ok: boolean; blocked: boolean; message: string | null }> {
    try {
      return await api.jumpManual(source);
    } catch (error) {
      return {
        ok: false,
        blocked: true,
        message:
          error instanceof ServiceError
            ? error.message
            : 'Erreur lors du saut manuel.',
      };
    }
  }

  /** Active ou désactive le mode accroupi manuel (déplacement lent, fluide et stable). */
  async toggleCrouchManual(): Promise<boolean> {
    const target = !(this.status.manualCrouchActive ?? false);
    try {
      const res = await api.crouchManual(target);
      if (res.blocked && res.message) {
        this.#setNotice('error', res.message);
      }
      return res.crouchActive;
    } catch (error) {
      this.#setNotice(
        'error',
        error instanceof ServiceError
          ? error.message
          : 'Erreur lors du changement de mode accroupi.',
      );
      return this.status.manualCrouchActive ?? false;
    }
  }

  /** Bascule l'état du mode autonome (marche avec évitement d'obstacles LiDAR). */
  async toggleAutonomous(): Promise<boolean> {
    try {
      const res = await api.toggleAutonomous();
      await this.refreshStatus();
      if (res.active) {
        this.status.obstacleSafetyEnabled = true;
        this.#setNotice('ok', 'Mode autonome activé : exploration avec sécurité obstacle verrouillée.');
      } else {
        this.#setNotice('ok', 'Mode autonome arrêté.');
      }
      return res.active;
    } catch (error) {
      this.#setNotice(
        'error',
        error instanceof ServiceError
          ? error.message
          : 'Impossible de basculer le mode autonome.',
      );
      return Boolean(this.status.autonomousActive);
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
      this.check(this.currentProgram);
    } catch (error) {
      this.#setNotice(
        'error',
        error instanceof ServiceError ? error.message : 'Changement de mode refusé.',
      );
      await this.refreshStatus();
    }
  }

  /**
   * Active ou coupe la vérification de place du SERVICE.
   *
   * Ce n'est PAS l'anti-obstacle du Go2 : celui-ci reste actif même quand
   * l'interrupteur est sur « arrêt ». Seuls le contrôle lidar du service et
   * son arrêt automatique sont concernés.
   */
  async setStandby(enabled: boolean): Promise<boolean> {
    try {
      const result = await api.setStandby(enabled);
      this.status.standby = result.standby;
      this.status.standbyTransition = result.standbyTransition;
      await this.refreshStatus();
      this.#setNotice(
        'ok',
        enabled
          ? 'Robot en veille prolongée (LiDAR et capteurs coupés pour économiser la batterie).'
          : 'Robot réveillé et prêt.',
      );
      return true;
    } catch (error) {
      this.#setNotice(
        'error',
        error instanceof ServiceError
          ? error.message
          : 'Impossible de modifier le mode veille.',
      );
      await this.refreshStatus();
      return false;
    }
  }

  async setObstacleSafety(enabled: boolean): Promise<boolean> {
    try {
      this.status = await api.setObstacleSafety(enabled, true);
      this.#setNotice(
        enabled ? 'ok' : 'warn',
        enabled
          ? 'Sécurité lidar du service activée.'
          : 'Sécurité lidar du service désactivée : l’anti-obstacle interne du Go2 reste actif.',
      );
      return true;
    } catch (error) {
      this.#setNotice(
        'error',
        error instanceof ServiceError
          ? error.message
          : 'Impossible de changer la sécurité lidar.',
      );
      await this.refreshStatus();
      return false;
    }
  }

  /** Ferme la fenêtre « pas assez de place ». */
  closeBlockedNotice(): void {
    this.blockedNotice = null;
  }

  /** Dernier programme compile, pour revalider apres un changement de mode. */
  currentProgram: Program = { statements: [] };

  setProgram(program: Program): void {
    this.currentProgram = program;
  }

  #onEvent(event: import('../api/client').ExecutionEvent): void {
    switch (event.type) {
      case 'autonomous_stopped':
        if (event.reason) {
          this.#setNotice('error', `Mode autonome désactivé : ${event.reason}`);
        }
        if (event.status) {
          this.status = event.status;
        }
        break;
      case 'status': {
        const wasAutonomous = Boolean(this.status.autonomousActive);
        const isAutonomous = Boolean(event.status.autonomousActive);
        if (wasAutonomous && !isAutonomous && event.status.autonomousStopReason) {
          this.#setNotice(
            'error',
            `Mode autonome désactivé : ${event.status.autonomousStopReason}`,
          );
        }
        this.status = event.status;
        break;
      }
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
        //
        // « bloqué » est une action NON faite : il n'y avait pas assez de
        // place d'après le lidar. Le programme continue, mais l'étape ne doit
        // pas être annoncée comme terminée.
        this.#updateStep(event.index, {
          state:
            event.outcome === 'exact'
              ? 'done'
              : event.outcome === 'blocked'
                ? 'blocked'
                : 'stopped',
          outcome:
            (event.outcome === 'blocked' || event.outcome === 'stopped') &&
            event.message
              ? event.message
              : describeOutcome(event.outcome, event.measured),
        });
        if (event.outcome === 'blocked') {
          this.blockedNotice = {
            title: blockedTitle(event.label),
            kind: 'blocked',
            message:
              event.message ??
              'Il n’y a pas assez de place pour ce pas. Le robot n’a pas bougé.',
          };
        } else if (
          event.outcome === 'stopped' &&
          event.message?.toLowerCase().includes('obstacle')
        ) {
          // Un obstacle est apparu PENDANT le pas : l'adaptateur a arrêté le
          // robot. Le message complet mérite la même fenêtre que le refus
          // avant le premier pas.
          this.blockedNotice = {
            title: 'Un obstacle est trop proche',
            kind: 'stopped',
            message: event.message,
          };
        }
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
        if (this.steps.some((step) => step.state === 'blocked')) {
          this.#setNotice(
            'warn',
            'Terminé ! Je n’ai pas fait les actions où il n’y avait pas assez de place.',
          );
        } else {
          this.#setNotice('ok', 'Terminé ! Le programme s’est bien déroulé.');
        }
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

/** Libelle en francais d'une instruction, delegue a `describe.ts`. */
export { describeStatement as describe } from '../robot/describe';

type Measured = { distanceCm?: number; angleDeg?: number } | null;

/** Titre court de la fenêtre d'obstacle, selon le pas concerné. */
function blockedTitle(label: string): string {
  if (label.startsWith('Reculer')) return 'Le robot ne peut pas reculer';
  if (label.startsWith('Aller à gauche')) return 'Le robot ne peut pas aller à gauche';
  if (label.startsWith('Aller à droite')) return 'Le robot ne peut pas aller à droite';
  return 'Le robot ne peut pas avancer';
}

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
    case 'blocked':
      return 'pas assez de place';
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