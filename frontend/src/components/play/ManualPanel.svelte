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
    s: 'backward',
    q: 'left',
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

    if (heldKeys.has('z') && !heldKeys.has('s')) linear = 'forward';
    else if (heldKeys.has('s') && !heldKeys.has('z')) linear = 'backward';

    if (
      (heldKeys.has('arrowleft') || heldKeys.has('left')) &&
      !(heldKeys.has('arrowright') || heldKeys.has('right'))
    ) {
      turn = 'turn_left';
    } else if (
      (heldKeys.has('arrowright') || heldKeys.has('right')) &&
      !(heldKeys.has('arrowleft') || heldKeys.has('left'))
    ) {
      turn = 'turn_right';
    }

    if (heldKeys.has('q') && !heldKeys.has('d')) strafe = 'left';
    else if (heldKeys.has('d') && !heldKeys.has('q')) strafe = 'right';

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
      if (result.blocked) {
        message = result.message ?? 'Le robot n’a pas pu sauter.';
      }
    } catch {
      message = 'Erreur de communication lors du saut.';
    } finally {
      isJumping = false;
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
    if (event.code === 'Space' || k === ' ') {
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
    if (event.code === 'Space' || k === ' ') {
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
      width: 170,
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
            title={activeSprint ? 'Sprint en cours (2,5 m/s)' : 'Avancer (0,6 m/s)'}
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
            title="Maintenir Shift (Maj) en avançant avec Z pour sprinter à 2,5 m/s"
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
            {activeSprint ? '⚡ SPRINT ACTIF (2,5 m/s)' : '⇧ Shift · Maintenir pour sprinter'}
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
        <li><strong>Shift + Z</strong> sprinter (vitesse max 2,5 m/s)</li>
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
    width: min(840px, 100%);
    padding: 22px 24px 18px;
    border: 1px solid #3d465a;
    border-radius: 24px;
    background: #1e222c;
    box-shadow: 0 16px 36px rgb(0 0 0 / 42%);
    color: #e6ebf5;
  }

  .manual__head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    padding-bottom: 14px;
    border-bottom: 1px solid rgb(255 255 255 / 8%);
  }

  .manual__identity {
    display: flex;
    align-items: center;
    gap: 12px;
  }

  .manual__icon {
    display: grid;
    place-items: center;
    width: 48px;
    height: 48px;
    flex: none;
    border-radius: 15px;
    background: linear-gradient(180deg, #8570e6, #6650c4);
    color: #fff;
    box-shadow: 0 6px 16px rgb(102 80 196 / 42%);
  }

  .manual__title {
    margin: 0;
    font-size: 24px;
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
    padding: 0 16px;
    border: 1px solid #4a5366;
    border-radius: 999px;
    background: rgb(255 255 255 / 5%);
    color: #d4daea;
    font: inherit;
    font-size: 13px;
    font-weight: 650;
    cursor: pointer;
    transition: background 0.15s ease;
  }

  .manual__close:hover {
    background: rgb(255 255 255 / 12%);
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
    margin: 12px 0 0;
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
    gap: 20px;
    margin-top: 14px;
  }

  .manual__pane {
    background: rgba(15, 23, 42, 0.45);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 18px;
    padding: 16px 18px;
    display: flex;
    flex-direction: column;
  }

  .manual__pane-title {
    display: flex;
    align-items: center;
    gap: 8px;
    margin: 0 0 8px;
    font-size: 15px;
    font-weight: 700;
    color: #93c5fd;
  }

  .manual__lead {
    margin: 0 0 12px;
    color: #c2cadb;
    font-size: 13px;
    line-height: 1.45;
  }

  .manual__lead strong {
    color: #f2f5fa;
  }

  .keypad {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 8px;
    margin: 0 auto 12px;
    user-select: none;
    touch-action: none;
  }

  .keypad__row {
    display: flex;
    gap: 8px;
  }

  .keypad__row--turns {
    width: 220px;
    justify-content: space-between;
  }

  .keypad__row--jump {
    width: 220px;
  }

  .keypad__row--sprint {
    width: 220px;
  }

  .key {
    display: grid;
    place-items: center;
    width: 66px;
    height: 56px;
    border: 1px solid #4a5366;
    border-radius: 14px;
    background: linear-gradient(180deg, #353b4b, #2b303d);
    color: #eef2fa;
    font: inherit;
    font-size: 22px;
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
    height: 46px;
    color: #cdd8ff;
    font-size: 24px;
  }

  .key--jump {
    width: 100%;
    height: 44px;
    font-size: 13.5px;
    font-weight: 650;
    letter-spacing: 0.02em;
    color: #e2e8f8;
  }

  .key--sprint {
    width: 100%;
    height: 42px;
    font-size: 13px;
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
    gap: 4px 14px;
    margin: 0 0 4px;
    padding: 0;
    list-style: none;
    color: #a9b4ca;
    font-size: 12px;
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
    margin: 0 0 12px;
    font-size: 12.5px;
    color: #94a3b8;
    line-height: 1.4;
  }

  .manual__qr-frame {
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 10px;
    background: #ffffff;
    border-radius: 14px;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.25);
    margin-bottom: 12px;
  }

  .manual__qr-img {
    display: block;
    width: 170px;
    height: 170px;
    border-radius: 6px;
  }

  .manual__qr-skeleton {
    width: 170px;
    height: 170px;
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
    max-width: 290px;
    padding: 4px 6px 4px 10px;
    background: rgba(255, 255, 255, 0.06);
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 8px;
    gap: 6px;
    margin-bottom: 12px;
  }

  .manual__qr-url-text {
    flex: 1;
    font-family: monospace;
    font-size: 11.5px;
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
    padding: 4px 8px;
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
    gap: 6px;
    width: 100%;
    max-width: 290px;
    margin-top: auto;
  }

  .qr-feature {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 11.5px;
    color: #93c5fd;
    background: rgba(59, 130, 246, 0.08);
    border: 1px solid rgba(59, 130, 246, 0.18);
    padding: 5px 10px;
    border-radius: 8px;
    text-align: left;
  }

  .manual__footer {
    display: flex;
    justify-content: flex-end;
    margin-top: 14px;
    padding-top: 10px;
    border-top: 1px solid rgb(255 255 255 / 8%);
    color: #9aa5b9;
    font-size: 12px;
  }

  .manual__stop {
    color: #c7d0e1;
    font-weight: 600;
  }

  @media (max-width: 780px) {
    .manual__grid {
      grid-template-columns: 1fr;
    }

    .manual {
      padding: 16px 14px 12px;
    }

    .keypad__row--turns,
    .keypad__row--jump,
    .keypad__row--sprint {
      width: 190px;
    }

    .key {
      width: 58px;
      height: 52px;
      font-size: 20px;
    }
  }
</style>
