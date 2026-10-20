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
  connectRobot: vi.fn(),
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

const { app } = await import('../src/lib/stores/app.svelte');

function programmeAssis() {
  return {
    statements: [{ kind: 'posture' as const, posture: 'sit' as const, line: 1 }],
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  apiMock.getStatus.mockResolvedValue({
    connected: true,
    mode: 'simulation',
    capabilities: [],
    executing: false,
    blockedReason: null,
    position: null,
    yawRad: null,
    batteryPercent: 100,
    posture: 'sit',
    settingsRevision: 0,
  });
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
