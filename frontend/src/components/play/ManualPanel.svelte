<script module lang="ts">
  /**
   * Numéro de séquence partagé par les sessions de cette page.
   *
   * Il ne repart pas à zéro quand le panneau est démonté : une requête lente
   * de l'ancienne session ne peut donc pas être prise pour une commande
   * nouvelle par le service.
   */
  let manualSequence = 0;

  export function nextManualSequence(): number {
    manualSequence += 1;
    return manualSequence;
  }
</script>

<script lang="ts">
  /**
   * Mode manuel : le robot répond à ZQSD, aux flèches, et à la barre Espace pour sauter.
   * Affiche directement à droite le QR code pour piloter depuis un smartphone.
   */
  import { onDestroy, onMount } from 'svelte';
  import { SvelteSet } from 'svelte/reactivity';
  import QRCode from 'qrcode';
  import Icon from './Icon.svelte';
  import { app } from '../../lib/stores/app.svelte';
  import type { ManualDirection, ManualMoveResult } from '../../lib/api/client';

  interface Props {
    /** Le robot réel est connecté : les touches peuvent le déplacer. */
    robotReady: boolean;
    onMove: (
      direction: ManualDirection,
      seq: number,
      sprint?: boolean,
    ) => Promise<ManualMoveResult>;
    onRelease: (seq: number) => void;
    onJump?: () => Promise<{ ok: boolean; blocked: boolean; message: string | null }>;
    onClose: () => void;
  }

  let { robotReady, onMove, onRelease, onJump, onClose }: Props = $props();

  const keyDirections: Record<string, string> = {
    z: 'forward',
    w: 'forward',
    arrowup: 'forward',
    up: 'forward',
    s: 'backward',
    arrowdown: 'backward',
    down: 'backward',
    q: 'left',
    a: 'left',
    d: 'right',
    arrowleft: 'turn_left',
    left: 'turn_left',
    arrowright: 'turn_right',
    right: 'turn_right',
  };

  const heldKeys = new SvelteSet<string>();
  let isShiftHeld = $state(false);
  let activeDirection = $state<ManualDirection | null>(null);
  let activeSprint = $state(false);
  let isJumping = $state(false);
  let message = $state<string | null>(null);
  let renewal: ReturnType<typeof setInterval> | null = null;
  let requestToken = 0;
  let inFlight = false;

  // QR Code direct pour le smartphone
  let qrDataUrl = $state<string | null>(null);
  let remoteUrl = $state('');
  let copied = $state(false);
  let copyTimeout: ReturnType<typeof setTimeout> | null = null;

  function computeRemoteUrl(): string {
    if (typeof window === 'undefined') return '';
    const protocol = window.location.protocol;
    const port = window.location.port ? `:${window.location.port}` : '';
    let host = window.location.hostname;
    if (host === 'localhost' || host === '127.0.0.1') {
      host = app.status.lanIp || '172.16.13.41';
    }
    return `${protocol}//${host}${port}/?remote=1`;
  }

  async function copyUrl(): Promise<void> {
    try {
      await navigator.clipboard.writeText(remoteUrl);
      copied = true;
      if (copyTimeout) clearTimeout(copyTimeout);
      copyTimeout = setTimeout(() => {
        copied = false;
      }, 2000);
    } catch {
      /* clipboard */
    }
  }

  function clearRenewal(): void {
    if (renewal !== null) {
      clearInterval(renewal);
      renewal = null;
    }
  }

  function hasOpenModal(): boolean {
    return document.querySelector('.modal-backdrop') !== null;
  }

  function isTypingTarget(target: EventTarget | null): boolean {
    if (!(target instanceof HTMLElement)) return false;
    return (
      target.isContentEditable ||
      ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName)
    );
  }

  function fail(reason: string | null): void {
    clearRenewal();
    requestToken += 1;
    heldKeys.clear();
    isShiftHeld = false;
    activeDirection = null;
    activeSprint = false;
    message = reason ?? 'Le robot s’est arrêté.';
    onRelease(nextManualSequence());
  }

  function resolveDirection(): ManualDirection | null {
    let linear: 'forward' | 'backward' | null = null;
    let turn: 'turn_left' | 'turn_right' | null = null;
    let strafe: 'left' | 'right' | null = null;

    const isForward =
      heldKeys.has('z') ||
      heldKeys.has('w') ||
      heldKeys.has('arrowup') ||
      heldKeys.has('up');
    const isBackward =
      heldKeys.has('s') ||
      heldKeys.has('arrowdown') ||
      heldKeys.has('down');

    if (isForward && !isBackward) linear = 'forward';
    else if (isBackward && !isForward) linear = 'backward';

    const isTurnLeft = heldKeys.has('arrowleft') || heldKeys.has('left');
    const isTurnRight = heldKeys.has('arrowright') || heldKeys.has('right');

    if (isTurnLeft && !isTurnRight) turn = 'turn_left';
    else if (isTurnRight && !isTurnLeft) turn = 'turn_right';

    const isLeft = heldKeys.has('q') || heldKeys.has('a');
    const isRight = heldKeys.has('d');

    if (isLeft && !isRight) strafe = 'left';
    else if (isRight && !isLeft) strafe = 'right';

    // Combinaisons avancer/reculer + tourner
    if (linear === 'forward' && turn === 'turn_left') return 'forward+turn_left';
    if (linear === 'forward' && turn === 'turn_right') return 'forward+turn_right';
    if (linear === 'backward' && turn === 'turn_left') return 'backward+turn_left';
    if (linear === 'backward' && turn === 'turn_right') return 'backward+turn_right';

    if (linear !== null) return linear;
    if (turn !== null) return turn;
    if (strafe !== null) return strafe;
    return null;
  }

  async function renew(
    direction: ManualDirection,
    sprint: boolean,
    token: number,
  ): Promise<void> {
    if (
      inFlight ||
      activeDirection !== direction ||
      activeSprint !== sprint ||
      token !== requestToken
    ) {
      return;
    }
    inFlight = true;
    try {
      const result = await onMove(direction, nextManualSequence(), sprint);
      void app.refreshStatus();
      if (
        token !== requestToken ||
        activeDirection !== direction ||
        activeSprint !== sprint
      ) {
        return;
      }
      if (result.blocked) {
        fail(result.message);
      }
    } finally {
      inFlight = false;
    }
  }

  async function updateMotion(): Promise<void> {
    if (isJumping || hasOpenModal()) return;

    const nextDir = resolveDirection();
    // Le sprint ne fonctionne qu'avec la touche Z (avancer), à la vitesse max (2,5 m/s)
    const nextSprint = Boolean(
      isShiftHeld && nextDir && nextDir.startsWith('forward'),
    );

    if (nextDir === activeDirection && nextSprint === activeSprint) return;

    if (nextDir === null) {
      clearRenewal();
      requestToken += 1;
      activeDirection = null;
      activeSprint = false;
      onRelease(nextManualSequence());
      return;
    }

    activeDirection = nextDir;
    activeSprint = nextSprint;
    message = null;

    if (!robotReady) return;

    const token = ++requestToken;
    const result = await onMove(nextDir, nextManualSequence(), nextSprint);
    void app.refreshStatus();
    if (
      token !== requestToken ||
      activeDirection !== nextDir ||
      activeSprint !== nextSprint
    ) {
      return;
    }

    if (result.blocked) {
      fail(result.message);
      return;
    }

    clearRenewal();
    renewal = setInterval(() => void renew(nextDir, nextSprint, token), 200);
  }

  async function triggerJump(): Promise<void> {
    if (isJumping || hasOpenModal() || !onJump) return;

    // Arrêt immédiat de toute consigne de déplacement continu
    heldKeys.clear();
    clearRenewal();
    requestToken += 1;
    activeDirection = null;
    activeSprint = false;
    onRelease(nextManualSequence());

    isJumping = true;
    message = null;
    try {
      const result = await onJump();
      void app.refreshStatus();
      if (result.blocked) {
        message = result.message ?? 'Le robot n’a pas pu sauter.';
      }
    } catch {
      message = 'Erreur de communication lors du saut.';
    } finally {
      setTimeout(() => {
        isJumping = false;
      }, 1500);
    }
  }

  function releaseAll(): void {
    heldKeys.clear();
    isShiftHeld = false;
    clearRenewal();
    requestToken += 1;
    if (activeDirection !== null || activeSprint) {
      activeDirection = null;
      activeSprint = false;
      onRelease(nextManualSequence());
    }
  }

  function onKeyDown(event: KeyboardEvent): void {
    if (event.repeat || event.ctrlKey || event.metaKey || event.altKey) return;
    if (isTypingTarget(event.target)) return;

    if (event.key === 'Shift') {
      event.preventDefault();
      event.stopPropagation();
      if (!isShiftHeld) {
        isShiftHeld = true;
        void updateMotion();
      }
      return;
    }

    const k = event.key.toLowerCase();
    if (event.code === 'Space' || k === ' ' || k === 'spacebar') {
      event.preventDefault();
      event.stopPropagation();
      void triggerJump();
      return;
    }

    if (keyDirections[k]) {
      event.preventDefault();
      event.stopPropagation();
      if (event.shiftKey) {
        isShiftHeld = true;
      }
      heldKeys.add(k);
      void updateMotion();
    }
  }

  function onKeyUp(event: KeyboardEvent): void {
    if (event.key === 'Shift') {
      event.preventDefault();
      event.stopPropagation();
      isShiftHeld = false;
      void updateMotion();
      return;
    }

    const k = event.key.toLowerCase();
    if (event.code === 'Space' || k === ' ' || k === 'spacebar') {
      event.preventDefault();
      event.stopPropagation();
      return;
    }

    if (keyDirections[k]) {
      event.preventDefault();
      event.stopPropagation();
      heldKeys.delete(k);
      if (!event.shiftKey && isShiftHeld) {
        isShiftHeld = false;
      }
      void updateMotion();
    }
  }

  function onVisibility(): void {
    if (document.visibilityState === 'hidden') releaseAll();
  }

  function onPointerDown(event: PointerEvent, key: string): void {
    event.preventDefault();
    const target = event.currentTarget;
    if (target instanceof HTMLElement) {
      target.setPointerCapture(event.pointerId);
    }
    heldKeys.add(key);
    void updateMotion();
  }

  function onPointerUp(event: PointerEvent, key: string): void {
    event.preventDefault();
    heldKeys.delete(key);
    void updateMotion();
  }

  function close(): void {
    releaseAll();
    onClose();
  }

  onMount(() => {
    remoteUrl = computeRemoteUrl();
    void QRCode.toDataURL(remoteUrl, {
      width: 180,
      margin: 1,
      color: {
        dark: '#1e293b',
        light: '#ffffff',
      },
    }).then((url) => {
      qrDataUrl = url;
    });

    window.addEventListener('keydown', onKeyDown, true);
    window.addEventListener('keyup', onKeyUp, true);
    window.addEventListener('blur', releaseAll);
    document.addEventListener('visibilitychange', onVisibility);
    return () => {
      if (copyTimeout) clearTimeout(copyTimeout);
      window.removeEventListener('keydown', onKeyDown, true);
      window.removeEventListener('keyup', onKeyUp, true);
      window.removeEventListener('blur', releaseAll);
      document.removeEventListener('visibilitychange', onVisibility);
    };
  });

  onDestroy(() => {
    clearRenewal();
    if (activeDirection !== null) onRelease(nextManualSequence());
  });
</script>

<section class="manual" aria-label="Mode manuel">
  <header class="manual__head">
    <div class="manual__identity">
      <span class="manual__icon" aria-hidden="true">
        <Icon name="gamepad" size={26} />
      </span>
      <div>
        <h2 class="manual__title">Mode manuel</h2>
        <p class="manual__subtitle">Tiens une touche, relâche pour t’arrêter</p>
      </div>
    </div>
    <div class="manual__actions">
      <button type="button" class="manual__close" onclick={close} title="Quitter le mode manuel">
        Quitter
      </button>
    </div>
  </header>

  {#if app.status.manualSource === 'mobile'}
    <div class="manual__source-badge" role="status">
      <Icon name="smartphone" size={16} />
      <span>📱 Contrôle mobile en cours depuis un smartphone...</span>
    </div>
  {/if}

  <!-- Grand rectangle réunissant les touches PC à gauche et le QR code mobile à droite -->
  <div class="manual__grid">
    <!-- Colonne Gauche : Touches Clavier PC -->
    <div class="manual__pane manual__pane--keyboard">
      <h3 class="manual__pane-title">
        <Icon name="gamepad" size={18} />
        <span>Clavier PC</span>
      </h3>
      <p class="manual__lead">
        Chaque touche fait bouger le robot <strong>tant qu’elle est tenue</strong>.
        Tu peux combiner <strong>Z</strong> et une flèche pour <strong>avancer en tournant</strong>.
      </p>

      <div class="keypad" aria-label="Touches de déplacement">
        <div class="keypad__row">
          <button
            type="button"
            class="key"
            class:key--on={heldKeys.has('z')}
            class:key--sprint-active={activeSprint}
            aria-label="Avancer"
            title={activeSprint ? 'Sprint en cours (vitesse max 3,5 m/s)' : 'Avancer (0,6 m/s)'}
            onpointerdown={(event) => onPointerDown(event, 'z')}
            onpointerup={(event) => onPointerUp(event, 'z')}
            onpointercancel={(event) => onPointerUp(event, 'z')}
            oncontextmenu={(event) => event.preventDefault()}
          >
            {activeSprint ? '⚡ Z' : 'Z'}
          </button>
        </div>
        <div class="keypad__row">
          <button
            type="button"
            class="key"
            class:key--on={heldKeys.has('q')}
            aria-label="Aller à gauche"
            onpointerdown={(event) => onPointerDown(event, 'q')}
            onpointerup={(event) => onPointerUp(event, 'q')}
            onpointercancel={(event) => onPointerUp(event, 'q')}
            oncontextmenu={(event) => event.preventDefault()}
          >
            Q
          </button>
          <button
            type="button"
            class="key"
            class:key--on={heldKeys.has('s')}
            aria-label="Reculer"
            onpointerdown={(event) => onPointerDown(event, 's')}
            onpointerup={(event) => onPointerUp(event, 's')}
            onpointercancel={(event) => onPointerUp(event, 's')}
            oncontextmenu={(event) => event.preventDefault()}
          >
            S
          </button>
          <button
            type="button"
            class="key"
            class:key--on={heldKeys.has('d')}
            aria-label="Aller à droite"
            onpointerdown={(event) => onPointerDown(event, 'd')}
            onpointerup={(event) => onPointerUp(event, 'd')}
            onpointercancel={(event) => onPointerUp(event, 'd')}
            oncontextmenu={(event) => event.preventDefault()}
          >
            D
          </button>
        </div>
        <div class="keypad__row keypad__row--turns">
          <button
            type="button"
            class="key key--turn"
            class:key--on={heldKeys.has('arrowleft') || heldKeys.has('left')}
            aria-label="Tourner à gauche"
            title="Tourner à gauche"
            onpointerdown={(event) => onPointerDown(event, 'arrowleft')}
            onpointerup={(event) => onPointerUp(event, 'arrowleft')}
            onpointercancel={(event) => onPointerUp(event, 'arrowleft')}
            oncontextmenu={(event) => event.preventDefault()}
          >
            ←
          </button>
          <button
            type="button"
            class="key key--turn"
            class:key--on={heldKeys.has('arrowright') || heldKeys.has('right')}
            aria-label="Tourner à droite"
            title="Tourner à droite"
            onpointerdown={(event) => onPointerDown(event, 'arrowright')}
            onpointerup={(event) => onPointerUp(event, 'arrowright')}
            onpointercancel={(event) => onPointerUp(event, 'arrowright')}
            oncontextmenu={(event) => event.preventDefault()}
          >
            →
          </button>
        </div>
        <div class="keypad__row keypad__row--sprint">
          <button
            type="button"
            class="key key--sprint"
            class:key--on={isShiftHeld}
            class:key--sprint-active={activeSprint}
            aria-label="Sprint Shift"
            title="Maintenir Shift (Maj) en avançant avec Z pour sprinter à la vitesse maximale (jusqu’à 3,5 m/s)"
            onpointerdown={(event) => {
              event.preventDefault();
              isShiftHeld = true;
              void updateMotion();
            }}
            onpointerup={(event) => {
              event.preventDefault();
              isShiftHeld = false;
              void updateMotion();
            }}
            onpointercancel={(event) => {
              event.preventDefault();
              isShiftHeld = false;
              void updateMotion();
            }}
            oncontextmenu={(event) => event.preventDefault()}
          >
            {activeSprint ? '⚡ SPRINT ACTIF (Vitesse max 3,5 m/s)' : '⇧ Shift · Maintenir pour sprinter'}
          </button>
        </div>
        {#if onJump}
          <div class="keypad__row keypad__row--jump">
            <button
              type="button"
              class="key key--jump"
              class:key--on={isJumping}
              aria-label="Sauter"
              title="Faire un saut (Espace)"
              disabled={isJumping}
              onclick={() => void triggerJump()}
            >
              {isJumping ? 'Saut en cours...' : 'Espace · Sauter'}
            </button>
          </div>
        {/if}
      </div>

      <ul class="manual__keys">
        <li><strong>Z</strong> avancer · <strong>S</strong> reculer</li>
        <li><strong>Q</strong> pas à gauche · <strong>D</strong> pas à droite</li>
        <li><strong>← / →</strong> tourner · <strong>Espace</strong> sauter</li>
        <li><strong>Shift + Z</strong> sprinter (vitesse max 3,5 m/s)</li>
      </ul>

      {#if message}
        <p class="manual__message" role="alert">{message}</p>
      {/if}
    </div>

    <!-- Colonne Droite : QR Code Téléphone Direct -->
    <div class="manual__pane manual__pane--qr">
      <h3 class="manual__pane-title">
        <Icon name="smartphone" size={18} />
        <span>Manette Téléphone</span>
      </h3>
      <p class="manual__qr-lead">
        Scannez ce QR code avec votre téléphone connecté au même réseau Wi-Fi.
      </p>

      <div class="manual__qr-frame">
        {#if qrDataUrl}
          <img
            class="manual__qr-img"
            src={qrDataUrl}
            alt="QR code pour piloter le Go2 depuis le smartphone"
          />
        {:else}
          <div class="manual__qr-skeleton">Génération du QR code...</div>
        {/if}
      </div>

      <div class="manual__qr-url-box">
        <span class="manual__qr-url-text">{remoteUrl}</span>
        <button
          type="button"
          class="manual__qr-copy-btn"
          onclick={copyUrl}
          title="Copier l'adresse"
        >
          {copied ? 'Copié !' : 'Copier'}
        </button>
      </div>

      <div class="manual__qr-features">
        <div class="qr-feature">
          <Icon name="smartphone" size={15} />
          <span>Mode paysage automatique</span>
        </div>
        <div class="qr-feature">
          <Icon name="gamepad" size={15} />
          <span>Joysticks tactiles ZQSD & rotation</span>
        </div>
        <div class="qr-feature">
          <Icon name="radar" size={15} />
          <span>Vue LiDAR 3D & Caméra en direct</span>
        </div>
      </div>
    </div>
  </div>

  <footer class="manual__footer">
    <span class="manual__stop">Relâche = arrêt immédiat</span>
  </footer>
</section>

<style>
  .manual {
    width: min(860px, 100%);
    padding: 18px 22px 14px;
    border: 1px solid #3d465a;
    border-radius: 22px;
    background: #1e222c;
    box-shadow: 0 16px 36px rgb(0 0 0 / 42%);
    color: #e6ebf5;
    box-sizing: border-box;
    display: flex;
    flex-direction: column;
  }

  .manual__head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    padding-bottom: 12px;
    border-bottom: 1px solid rgb(255 255 255 / 8%);
    flex: none;
  }

  .manual__identity {
    display: flex;
    align-items: center;
    gap: 12px;
  }

  .manual__icon {
    display: grid;
    place-items: center;
    width: 44px;
    height: 44px;
    flex: none;
    border-radius: 13px;
    background: linear-gradient(180deg, #8570e6, #6650c4);
    color: #fff;
    box-shadow: 0 5px 14px rgb(102 80 196 / 42%);
  }

  .manual__title {
    margin: 0;
    font-size: 22px;
    letter-spacing: -0.02em;
    color: #f2f5fa;
  }

  .manual__subtitle {
    margin: 2px 0 0;
    color: #a9b4ca;
    font-size: 13px;
  }

  .manual__actions {
    display: flex;
    align-items: center;
    gap: 10px;
  }

  .manual__close {
    min-height: 38px;
    padding: 0 18px;
    border: 1px solid #4a5366;
    border-radius: 999px;
    background: rgb(255 255 255 / 6%);
    color: #d4daea;
    font: inherit;
    font-size: 13.5px;
    font-weight: 650;
    cursor: pointer;
    transition: background 0.15s ease;
  }

  .manual__close:hover {
    background: rgb(255 255 255 / 14%);
  }

  .manual__close:focus-visible,
  .key:focus-visible {
    outline: 2px solid #cfe0f5;
    outline-offset: 2px;
  }

  .manual__source-badge {
    display: flex;
    align-items: center;
    gap: 8px;
    margin: 10px 0 0;
    padding: 8px 14px;
    background: rgba(59, 130, 246, 0.15);
    border: 1px solid rgba(59, 130, 246, 0.35);
    border-radius: 10px;
    color: #93c5fd;
    font-size: 13px;
    font-weight: 500;
  }

  /* Grille deux colonnes réunissant les touches PC et le QR code */
  .manual__grid {
    display: grid;
    grid-template-columns: 1.15fr 0.85fr;
    gap: 16px;
    margin-top: 12px;
  }

  .manual__pane {
    background: rgba(15, 23, 42, 0.45);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 16px;
    padding: 14px 16px;
    display: flex;
    flex-direction: column;
  }

  .manual__pane-title {
    display: flex;
    align-items: center;
    gap: 8px;
    margin: 0 0 6px;
    font-size: 15px;
    font-weight: 700;
    color: #93c5fd;
  }

  .manual__lead {
    margin: 0 0 8px;
    color: #c2cadb;
    font-size: 12.5px;
    line-height: 1.4;
  }

  .manual__lead strong {
    color: #f2f5fa;
  }

  .keypad {
    --key-w: 66px;
    --key-gap: 6px;
    --keypad-w: calc(var(--key-w) * 3 + var(--key-gap) * 2);

    display: flex;
    flex-direction: column;
    align-items: center;
    gap: var(--key-gap);
    margin: 0 auto 8px;
    user-select: none;
    touch-action: none;
  }

  .keypad__row {
    display: flex;
    gap: var(--key-gap);
  }

  .keypad__row--turns,
  .keypad__row--jump,
  .keypad__row--sprint {
    width: var(--keypad-w);
  }

  .keypad__row--turns {
    justify-content: space-between;
  }

  .key {
    display: grid;
    place-items: center;
    width: var(--key-w);
    height: 52px;
    border: 1px solid #4a5366;
    border-radius: 13px;
    background: linear-gradient(180deg, #353b4b, #2b303d);
    color: #eef2fa;
    font: inherit;
    font-size: 21px;
    font-weight: 750;
    cursor: pointer;
    box-shadow:
      inset 0 1px 0 rgb(255 255 255 / 8%),
      0 4px 10px rgb(0 0 0 / 24%);
    transition:
      transform 0.08s ease,
      background 0.12s ease,
      border-color 0.12s ease;
  }

  .key--turn {
    height: 44px;
    color: #cdd8ff;
    font-size: 22px;
  }

  .key--jump {
    width: 100%;
    height: 40px;
    font-size: 13px;
    font-weight: 650;
    letter-spacing: 0.02em;
    color: #e2e8f8;
  }

  .key--sprint {
    width: 100%;
    height: 38px;
    font-size: 12.5px;
    font-weight: 700;
    letter-spacing: 0.02em;
    color: #e0e7ff;
    background: linear-gradient(180deg, #374151, #1f2937);
    border-color: #4b5563;
  }

  .key--on {
    transform: translateY(2px);
    border-color: #9b87f0;
    background: linear-gradient(180deg, #7c68df, #5f49bb);
    box-shadow:
      inset 0 2px 8px rgb(0 0 0 / 22%),
      0 0 18px rgb(126 108 232 / 35%);
  }

  .key--sprint-active {
    border-color: #f59e0b !important;
    background: linear-gradient(180deg, #f59e0b, #d97706) !important;
    color: #ffffff !important;
    box-shadow:
      inset 0 2px 8px rgb(0 0 0 / 22%),
      0 0 22px rgb(245 158 11 / 55%) !important;
    transform: translateY(2px);
  }

  .manual__keys {
    display: flex;
    flex-wrap: wrap;
    justify-content: center;
    gap: 3px 12px;
    margin: 0;
    padding: 0;
    list-style: none;
    color: #a9b4ca;
    font-size: 11.5px;
  }

  .manual__keys strong {
    color: #e7ecf7;
  }

  .manual__message {
    margin: 8px 0 0;
    padding: 8px 12px;
    border: 1px solid #7f3841;
    border-radius: 10px;
    background: rgb(198 62 74 / 14%);
    color: #f3b0b7;
    font-size: 12.5px;
    line-height: 1.4;
  }

  /* Panneau QR Code à droite */
  .manual__pane--qr {
    align-items: center;
    text-align: center;
  }

  .manual__qr-lead {
    margin: 0 0 8px;
    font-size: 12px;
    color: #94a3b8;
    line-height: 1.35;
  }

  .manual__qr-frame {
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 8px;
    background: #ffffff;
    border-radius: 12px;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.25);
    margin-bottom: 8px;
  }

  .manual__qr-img {
    display: block;
    width: 155px;
    height: 155px;
    border-radius: 6px;
  }

  .manual__qr-skeleton {
    width: 155px;
    height: 155px;
    display: flex;
    align-items: center;
    justify-content: center;
    color: #64748b;
    font-size: 12px;
  }

  .manual__qr-url-box {
    display: flex;
    align-items: center;
    width: 100%;
    max-width: 270px;
    padding: 3px 6px 3px 10px;
    background: rgba(255, 255, 255, 0.06);
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 8px;
    gap: 6px;
    margin-bottom: 8px;
  }

  .manual__qr-url-text {
    flex: 1;
    font-family: monospace;
    font-size: 11px;
    color: #cbd5e1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    text-align: left;
  }

  .manual__qr-copy-btn {
    border: none;
    background: #2563eb;
    color: #ffffff;
    font-size: 11px;
    font-weight: 600;
    padding: 3px 8px;
    border-radius: 6px;
    cursor: pointer;
    transition: background 0.15s;
  }

  .manual__qr-copy-btn:hover {
    background: #3b82f6;
  }

  .manual__qr-features {
    display: flex;
    flex-direction: column;
    gap: 5px;
    width: 100%;
    max-width: 270px;
    margin-top: auto;
  }

  .qr-feature {
    display: flex;
    align-items: center;
    gap: 7px;
    font-size: 11px;
    color: #93c5fd;
    background: rgba(59, 130, 246, 0.08);
    border: 1px solid rgba(59, 130, 246, 0.18);
    padding: 4px 10px;
    border-radius: 7px;
    text-align: left;
  }

  .manual__footer {
    display: flex;
    justify-content: flex-end;
    margin-top: 10px;
    padding-top: 8px;
    border-top: 1px solid rgb(255 255 255 / 8%);
    color: #9aa5b9;
    font-size: 12px;
    flex: none;
  }

  .manual__stop {
    color: #c7d0e1;
    font-weight: 600;
  }

  /* Grands écrans PC fixe (>= 1700px) */
  @media (min-width: 1700px) {
    .manual {
      width: min(940px, 100%);
      padding: 22px 26px 16px;
    }

    .manual__icon {
      width: 48px;
      height: 48px;
    }

    .manual__title {
      font-size: 24px;
    }

    .manual__subtitle {
      font-size: 14px;
    }

    .manual__grid {
      gap: 20px;
      margin-top: 14px;
    }

    .manual__pane {
      padding: 16px 20px;
    }

    .keypad {
      --key-w: 70px;
      --key-gap: 8px;
    }

    .key {
      height: 56px;
      font-size: 22px;
    }

    .key--turn {
      height: 46px;
      font-size: 24px;
    }

    .key--sprint {
      height: 42px;
      font-size: 13px;
    }

    .key--jump {
      height: 44px;
      font-size: 13.5px;
    }

    .manual__qr-img,
    .manual__qr-skeleton {
      width: 170px;
      height: 170px;
    }

    .manual__qr-url-box,
    .manual__qr-features {
      max-width: 290px;
    }
  }

  @media (max-width: 640px) {
    .manual__grid {
      grid-template-columns: 1fr;
    }

    .manual {
      padding: 14px 12px 10px;
    }

    .keypad {
      --key-w: 54px;
      --key-gap: 5px;
    }

    .key {
      height: 42px;
      font-size: 18px;
    }
  }
</style>
