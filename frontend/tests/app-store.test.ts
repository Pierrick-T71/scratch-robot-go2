/**
 * Course entre la réponse HTTP et les événements d'exécution.
 *
 * Un programme très court (une seule posture) se termine en quelques
 * millisecondes : l'événement de fin passe alors AVANT la réponse HTTP. Si
 * l'interface repassait en « en cours » après cette réponse, elle resterait
 * bloquée sur un programme arrêté : bouton « Lancer » désactivé, aucun
 * bloc ajoutable, aucune nouvelle exécution possible.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import type { ExecutionEvent } from '../src/lib/api/client';

/** Rappel des événements : le test joue le rôle du WebSocket. */
let recoir: ((event: ExecutionEvent) => void) | null = null;

const apiMock = {
  start: vi.fn(),
  stop: vi.fn(),
  getStatus: vi.fn(),
  heartbeat: vi.fn(),
  getSettings: vi.fn(),
  saveSettings: vi.fn(),
  setMode: vi.fn(),
  setObstacleSafety: vi.fn(),
  connectRobot: vi.fn(),
  jumpManual: vi.fn(),
  setStandby: vi.fn(),
  resetSimulation: vi.fn(),
};

vi.mock('../src/lib/api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../src/lib/api/client')>();
  return {
    ...actual,
    api: apiMock,
    EventStream: class {
      constructor(onEvent: (event: ExecutionEvent) => void) {
        recoir = onEvent;
      }
      connect(): void {}
      disconnect(): void {}
    },
  };
});

const { app, describeOutcome } = await import('../src/lib/stores/app.svelte');

function programmeAssis() {
  return {
    statements: [{ kind: 'posture' as const, posture: 'sit' as const, line: 1 }],
  };
}

function statutDeBase() {
  return {
    connected: true,
    mode: 'simulation' as const,
    capabilities: [],
    executing: false,
    blockedReason: null,
    safetyReason: null,
    recoveryReason: null,
    position: null,
    yawRad: null,
    batteryPercent: 100,
    posture: 'sit',
    settingsRevision: 0,
    obstacleSafetyEnabled: true,
    obstacleSafetyAvailable: true,
    standby: false,
    standbyTransition: null,
    manualSource: null,
    lanIp: '172.16.13.41',
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  app.blockedNotice = null;
  app.notice = null;
  apiMock.getStatus.mockResolvedValue(statutDeBase());
  app.connect();
});

describe('fin avant la réponse', () => {
  it('ne rouvre pas une exécution déjà terminée', async () => {
    apiMock.start.mockImplementation(async () => {
      // Le service termine le programme ET prévient le frontend avant de
      // répondre à l'appel HTTP.
      recoir?.({
        type: 'execution_finished',
        reason: 'completed',
      } as ExecutionEvent);
      return { runId: 'run-1' };
    });

    app.requestStart(programmeAssis());
    await new Promise((resolve) => setTimeout(resolve, 0));

    expect(app.isBusy).toBe(false);
    expect(app.notice?.message).toContain('Terminé');
  });

  it('repart normalement quand la réponse arrive avant la fin', async () => {
    apiMock.start.mockImplementation(async () => {
      // La réponse arrive, le programme finit ensuite.
      setTimeout(() => {
        recoir?.({
          type: 'execution_finished',
          reason: 'completed',
        } as ExecutionEvent);
      }, 0);
      return { runId: 'run-2' };
    });

    app.requestStart(programmeAssis());
    await new Promise((resolve) => setTimeout(resolve, 5));

    expect(app.isBusy).toBe(false);
    expect(app.notice?.message).toContain('Terminé');
  });
});

describe('action bloquée par un obstacle', () => {
  it('garde la trace de l’étape non faite et le dit à la fin', async () => {
    apiMock.start.mockResolvedValue({ runId: 'run-3' });
    const programme = {
      statements: [
        {
          kind: 'move' as const,
          direction: 'forward' as const,
          seconds: 5,
          line: 1,
        },
        { kind: 'posture' as const, posture: 'sit' as const, line: 2 },
      ],
    };

    app.requestStart(programme);
    await new Promise((resolve) => setTimeout(resolve, 0));

    const message = 'Pas assez de place devant : il reste 0,5 m libres.';
    recoir?.({ type: 'step_started', index: 0, label: 'avancer' });
    recoir?.({
      type: 'step_finished',
      index: 0,
      label: 'avancer',
      outcome: 'blocked',
      measured: null,
      message,
    } as ExecutionEvent);
    recoir?.({ type: 'execution_finished', reason: 'completed' });

    expect(app.steps[0].state).toBe('blocked');
    expect(app.steps[0].outcome).toBe(message);
    expect(app.notice?.tone).toBe('warn');
    expect(app.notice?.message).toContain('pas assez de place');
    expect(app.blockedNotice?.title).toBe('Le robot ne peut pas avancer');
    expect(app.blockedNotice?.kind).toBe('blocked');
    expect(app.blockedNotice?.message).toBe(message);

    app.closeBlockedNotice();
    expect(app.blockedNotice).toBeNull();
  });

  it('sait nommer une étape bloquée quand le service ne détaille pas', () => {
    expect(describeOutcome('blocked', null)).toBe('pas assez de place');
  });

  it('affiche aussi la fenêtre quand un obstacle apparaît pendant le pas', () => {
    const message =
      'Un obstacle est trop proche devant : je me suis arrêté.';

    recoir?.({
      type: 'step_finished',
      index: 0,
      label: 'avancer',
      outcome: 'stopped',
      measured: null,
      message,
    } as ExecutionEvent);

    expect(app.blockedNotice?.title).toBe('Un obstacle est trop proche');
    expect(app.blockedNotice?.kind).toBe('stopped');
    expect(app.blockedNotice?.message).toBe(message);
  });
});

describe('interrupteur de sécurité lidar', () => {
  it('coupe puis réactive la vérification de place du service', async () => {
    apiMock.setObstacleSafety
      .mockResolvedValueOnce({
        ...statutDeBase(),
        mode: 'real' as const,
        obstacleSafetyEnabled: false,
      })
      .mockResolvedValueOnce({
        ...statutDeBase(),
        mode: 'real' as const,
        obstacleSafetyEnabled: true,
      });

    const coupe = await app.setObstacleSafety(false);

    expect(coupe).toBe(true);
    expect(apiMock.setObstacleSafety).toHaveBeenLastCalledWith(false, true);
    expect(app.status.obstacleSafetyEnabled).toBe(false);
    expect(app.notice?.tone).toBe('warn');
    expect(app.notice?.message).toContain('désactivée');

    const remis = await app.setObstacleSafety(true);

    expect(remis).toBe(true);
    expect(apiMock.setObstacleSafety).toHaveBeenLastCalledWith(true, true);
    expect(app.status.obstacleSafetyEnabled).toBe(true);
    expect(app.notice?.message).toContain('activée');
  });
});

describe('interrupteur de veille', () => {
  it('active puis coupe le mode veille', async () => {
    apiMock.setStandby
      .mockResolvedValueOnce({ standby: true, standbyTransition: null })
      .mockResolvedValueOnce({ standby: false, standbyTransition: null });
    apiMock.getStatus
      .mockResolvedValueOnce({ ...statutDeBase(), standby: true })
      .mockResolvedValueOnce({ ...statutDeBase(), standby: false });

    const actif = await app.setStandby(true);
    expect(actif).toBe(true);
    expect(apiMock.setStandby).toHaveBeenCalledWith(true);
    expect(app.status.standby).toBe(true);
    expect(app.isBusy).toBe(true);

    const reveil = await app.setStandby(false);
    expect(reveil).toBe(true);
    expect(apiMock.setStandby).toHaveBeenCalledWith(false);
    expect(app.status.standby).toBe(false);
    expect(app.isBusy).toBe(false);
  });
});

describe('mode autonome', () => {
  it('affiche un message d’erreur explicite quand il est arrêté sur obstacle', () => {
    recoir?.({
      type: 'autonomous_stopped',
      reason: 'Obstacle détecté devant le robot (38 cm).',
      status: {
        ...statutDeBase(),
        autonomousActive: false,
        autonomousStopReason: 'Obstacle détecté devant le robot (38 cm).',
      },
    } as ExecutionEvent);

    expect(app.notice?.tone).toBe('error');
    expect(app.notice?.message).toBe(
      'Mode autonome désactivé : Obstacle détecté devant le robot (38 cm).',
    );
    expect(app.status.autonomousActive).toBe(false);
  });
});

describe('réinitialisation de la simulation', () => {
  it('remet la position et le cap au centre et appelle le service', async () => {
    app.status.position = { x: 1.5, y: 0.8, z: 0 };
    app.status.yawRad = 1.2;

    apiMock.resetSimulation.mockResolvedValueOnce({
      ok: true,
      status: {
        ...statutDeBase(),
        position: { x: 0, y: 0, z: 0 },
        yawRad: 0,
      },
    });

    await app.resetSimulation();

    expect(apiMock.resetSimulation).toHaveBeenCalled();
    expect(app.status.position).toEqual({ x: 0, y: 0, z: 0 });
    expect(app.status.yawRad).toBe(0);
  });
});
