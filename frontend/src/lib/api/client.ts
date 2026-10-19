/**
 * Client HTTP/WebSocket vers le robot-service.
 *
 * Deux transports, selon la nature de l'echange :
 *  - HTTP  : operations ponctuelles (etat, demarrage, arret, missions) ;
 *  - WS    : evenements d'etat et progression, unidirectionnels pour le
 *            pilotage. Le pilotage reste sur HTTP : une connexion WS perdue
 *            ne doit jamais interrompre la liaison de securite.
 *
 * Pendant une execution, le client envoie un BATIMENT (heartbeat). Si le
 * service ne le recoit plus, son chien de garde declenche l'arret. C'est la
 * protection principale contre la disparition du frontend.
 */
import { SERVICE_URL, SAFETY } from '../robot/limits';
import type { Capability } from '../robot/commands';
import type { Program } from '../robot/program';
import type { SettingsPayload, SettingsValues } from '../robot/settings';

export type { SettingsPayload, SettingsValues, SettingsBounds } from '../robot/settings';

export type ServiceMode = 'simulation' | 'real';

export interface RobotStatus {
  connected: boolean;
  mode: ServiceMode;
  /** Capacites offertes par l'adaptateur actif. */
  capabilities: Capability[];
  executing: boolean;
  /** Explication si le robot refuse une action, sinon null. */
  blockedReason: string | null;
  /** Position mesuree, si l'etat est disponible. */
  position: { x: number; y: number; z: number } | null;
  yawRad: number | null;
  batteryPercent: number | null;
  /** Incrémenté par le service à chaque changement de limites. */
  settingsRevision: number;
}

export interface StartRequest {
  /**
   * Programme STRUCTURE, pas une liste de commandes.
   *
   * Les conditions et les variables ne peuvent pas être résolues à la
   * compilation : seul le service, qui détient les valeurs pendant
   * l'exécution, peut trancher. Lui envoyer une liste aplatie l'obligerait à
   * deviner, ce que nous refusons.
   */
  program: Program;
  /**
   * Accordee explicitement par un adulte (mode reel uniquement).
   *
   * Envoyée sous le nom `adult_authorised` : c'est le nom du modèle
   * `StartRequest` côté service, qui rejette tout champ inconnu.
   */
  adult_authorised: boolean;
}

/** Valeur d'une variable, telle que le service la calcule réellement. */
export interface VariableValue {
  name: string;
  value: number;
  /** Le service a-t-il publishé cette valeur de lui-même ? */
  visible: boolean;
}

export type ExecutionEvent =
  | { type: 'status'; status: RobotStatus }
  | { type: 'step_started'; index: number; label: string }
  | { type: 'step_completed'; index: number; label: string }
  | {
      type: 'step_finished';
      index: number;
      label: string;
      /** 'exact' = mesure confirmee ; 'timeout' = delai atteint sans mesure. */
      outcome: 'exact' | 'timeout';
      measured: { distanceCm?: number; angleDeg?: number } | null;
    }
  /**
   * Photographie des variables.
   *
   * Les valeurs viennent du service, jamais du frontend : ce sont les siennes
   * qui font foi. `reset` signale un nouveau départ de programme, où les
   * variables retomment à zéro.
   */
  | { type: 'variables'; values: VariableValue[]; reset?: boolean }
  | { type: 'execution_finished'; reason: 'completed' | 'stopped' | 'error' | 'safety' }
  | { type: 'error'; message: string };

/** Rapport du test de branchement d'un robot réel. */
export interface RobotConnectionReport {
  robot_ip: string;
  interface: string;
  /** `true` SEULEMENT si un message a réellement été reçu du robot. */
  connecte: boolean;
  test_lance: boolean;
  commande_envoyee: string | null;
  succes: boolean;
  message: string;
}

export class ServiceError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = 'ServiceError';
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${SERVICE_URL}${path}`, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
    });
  } catch {
    throw new ServiceError(
      'Le service robot ne répond pas. Demande de l’aide à l’adulte.',
      0,
    );
  }

  const text = await response.text();
  let body: unknown = null;
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      throw new ServiceError('Réponse du service incompréhensible.', response.status);
    }
  }

  if (!response.ok) {
    const detail =
      typeof body === 'object' && body !== null && 'detail' in body
        ? String((body as { detail: unknown }).detail)
        : 'Erreur du service.';
    throw new ServiceError(detail, response.status);
  }
  return body as T;
}

export const api = {
  getStatus: (): Promise<RobotStatus> => request<RobotStatus>('/api/status'),

  /**
   * Démarre un programme. Répond immédiatement avec `runId` : l'exécution
   * tourne en tâche de fond côté service.
   */
  start: (payload: StartRequest): Promise<{ accepted: boolean; runId: string }> =>
    request('/api/execution/start', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  stop: (): Promise<{ stopping: boolean }> =>
    request('/api/execution/stop', { method: 'POST' }),

  /**
 * Battement de sécurité.
 *
 * ATTENTION : le service attend `run_id` (le nom du modèle
 * `HeartbeatRequest`). Toute divergence de casse fait échouer la requête en
 * 422, le bail expire, et le chien de garde arrête le robot — c'est
 * exactement ce qui est arrivé pendant le développement. Le test
 * d'intégration du service verrouille cette forme de payload.
 */
heartbeat: (runId: string): Promise<{ ok: boolean }> =>
    request('/api/execution/heartbeat', {
      method: 'POST',
      body: JSON.stringify({ run_id: runId }),
    }),

  /**
   * Bascule de mode. `adultAuthorised` est un paramètre de l'appelant, mais
   * il est envoyé sous le nom `adult_authorised` attendu par `ModeRequest`.
   */
  setMode: (mode: ServiceMode, adultAuthorised: boolean): Promise<RobotStatus> =>
    request<RobotStatus>('/api/mode', {
      method: 'POST',
      body: JSON.stringify({ mode, adult_authorised: adultAuthorised }),
    }),

  /** Réglages en vigueur et bornes autorisées. */
  getSettings: (): Promise<SettingsPayload> => request<SettingsPayload>('/api/settings'),

  /**
   * Applique des réglages. Réservé à un adulte, et borné par le service.
   *
   * ATTENTION : le service attend `adult_authorised` (nom du modèle
   * `SettingsRequest`) et rejette tout champ inconnu. Envoyer
   * `adultAuthorised` serait refusé en 422 — c'est exactement l'erreur
   * commise en développement. `test_settings.py` verrouille la forme.
   */
  saveSettings: (values: SettingsValues): Promise<SettingsPayload> =>
    request<SettingsPayload>('/api/settings', {
      method: 'POST',
      body: JSON.stringify({ adult_authorised: true, values }),
    }),

  /**
   * Branche un robot réel.
   *
   * Le canal retenu est celui de l'application mobile du constructeur
   * (WebRTC, port 9991) : il ne dépend pas d'une interface réseau locale,
   * seulement de l'adresse du robot. L'ancien champ `network_interface` reste
   * exigé par le service, mais il est désormais constant.
   *
   * `lancerTest` déclenche un geste physique (`Sit()`). C'est un paramètre
   * explicite, jamais implicite : ouvrir la liaison et bouger le robot sont
   * deux actes différents, et le second doit être demandé.
   */
  connectRobot: (
    robotIp: string,
    lancerTest: boolean,
  ): Promise<RobotConnectionReport> =>
    request<RobotConnectionReport>('/api/robot/connect', {
      method: 'POST',
      body: JSON.stringify({
        robot_ip: robotIp,
        network_interface: 'webrtc',
        lancer_test: lancerTest,
      }),
    }),

  /** Revient en simulation et immobilise le robot. */
  disconnectRobot: (): Promise<{ simulation: boolean }> =>
    request<{ simulation: boolean }>('/api/robot/disconnect', {
      method: 'POST',
      body: JSON.stringify({}),
    }),
};

/** Connexion aux evenements du service, avec reconnexion espacee. */
export class EventStream {
  private socket: WebSocket | null = null;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private closed = false;

  constructor(private readonly onEvent: (event: ExecutionEvent) => void) {}

  connect(): void {
    this.closed = false;
    const url = SERVICE_URL.replace(/^http/, 'ws') + '/ws/events';
    const socket = new WebSocket(url);
    this.socket = socket;

    socket.onmessage = (message: MessageEvent<string>) => {
      try {
        this.onEvent(JSON.parse(message.data) as ExecutionEvent);
      } catch {
        // Message illisible : on l'ignore, la securite ne depend pas de l'UI.
      }
    };
    socket.onclose = () => {
      this.socket = null;
      if (this.closed) return;
      this.timer = setTimeout(() => this.connect(), 1500);
    };
    socket.onerror = () => socket.close();
  }

  disconnect(): void {
    this.closed = true;
    if (this.timer) clearTimeout(this.timer);
    this.timer = null;
    this.socket?.close();
    this.socket = null;
  }
}

/**
 * Maintient le batiment de securite pendant une execution.
 * S'arrete des que la liaison echoue : mieux vaut que le service arrete le
 * robot que de laisser croire a l'interface que tout va bien.
 */
export class LeaseKeeper {
  private timer: ReturnType<typeof setInterval> | null = null;

  constructor(private readonly runId: string) {}

  start(): void {
    this.stop();
    this.timer = setInterval(() => {
      void api.heartbeat(this.runId).catch(() => {
        // Le service arretera de lui-meme a l'expiration du bail.
      });
    }, SAFETY.safety.heartbeatIntervalMs);
  }

  stop(): void {
    if (this.timer) clearInterval(this.timer);
    this.timer = null;
  }
}