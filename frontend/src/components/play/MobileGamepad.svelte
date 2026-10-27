<script lang="ts">
  /**
   * Manette mobile en mode paysage pour piloter le Go2 Pro.
   *
   * Optimisée pour iPhone (iPhone 16 et écrans tactiles récents) :
   *  - Utilisation de 100dvh et des safe-area insets pour éviter tout débordement
   *  - Dimensions adaptées pour que le bouton Sauter et les joysticks soient 100% visibles
   *  - Bouton Plein Écran pour masquer la barre d'adresse et les onglets du navigateur
   *  - Joystick gauche 2D (ZQSD) et joystick droit (rotation)
   */
  import { onMount, onDestroy } from 'svelte';
  import Icon from './Icon.svelte';
  import LidarScene from './LidarScene.svelte';
  import { app } from '../../lib/stores/app.svelte';
  import { api, type LidarVolume, type ManualDirection } from '../../lib/api/client';
  import { SERVICE_URL } from '../../lib/robot/limits';
  import { nextManualSequence } from './ManualPanel.svelte';

  let isPortrait = $state(false);
  let viewMode = $state<'lidar' | 'camera'>('lidar');
  let cameraFailed = $state(false);
  let lidarVolume = $state<LidarVolume | null>(null);

  // Plein écran
  let isFullscreen = $state(false);
  let showIosTip = $state(false);
  let tipTimer: ReturnType<typeof setTimeout> | null = null;

  // Joystick gauche : 2D (Avance/Recul = Z/S, Gauche/Droite = Q/D)
  let leftX = $state(0);
  let leftY = $state(0);
  let leftDir = $state<'forward' | 'backward' | 'left' | 'right' | null>(null);
  let leftActive = $state(false);

  // Joystick droit : horizontal uniquement (rotation gauche/droite)
  let rightX = $state(0);
  let rightTurn = $state<'turn_left' | 'turn_right' | null>(null);
  let rightActive = $state(false);

  let activeDirection = $state<ManualDirection | null>(null);
  let isJumping = $state(false);
  let feedbackMessage = $state<string | null>(null);

  let renewalTimer: ReturnType<typeof setInterval> | null = null;
  let lidarPollingActive = true;

  // Rayon et seuil adaptés aux écrans compacts en paysage
  const MAX_RADIUS = 36;
  const THRESHOLD = 12;
  const cameraUrl = `${SERVICE_URL}/api/robot/camera`;

  function checkOrientation(): void {
    if (typeof window !== 'undefined') {
      isPortrait = window.innerHeight > window.innerWidth;
    }
  }

  function updateFullscreenState(): void {
    if (typeof document !== 'undefined') {
      const doc = document as Document & { webkitFullscreenElement?: Element };
      isFullscreen = Boolean(doc.fullscreenElement || doc.webkitFullscreenElement);
    }
  }

  async function toggleFullscreen(): Promise<void> {
    if (typeof document === 'undefined') return;
    const doc = document as Document & {
      webkitFullscreenElement?: Element;
      webkitExitFullscreen?: () => Promise<void>;
    };
    const el = document.documentElement as HTMLElement & {
      webkitRequestFullscreen?: () => Promise<void>;
    };

    try {
      if (!doc.fullscreenElement && !doc.webkitFullscreenElement) {
        if (el.requestFullscreen) {
          await el.requestFullscreen();
        } else if (el.webkitRequestFullscreen) {
          await el.webkitRequestFullscreen();
        } else {
          // iOS Safari sur iPhone ne permet pas requestFullscreen sur l'élément document
          triggerIosTip();
        }
      } else {
        if (doc.exitFullscreen) {
          await doc.exitFullscreen();
        } else if (doc.webkitExitFullscreen) {
          await doc.webkitExitFullscreen();
        }
      }
    } catch {
      triggerIosTip();
    }
    updateFullscreenState();
  }

  function triggerIosTip(): void {
    showIosTip = true;
    if (tipTimer) clearTimeout(tipTimer);
    tipTimer = setTimeout(() => {
      showIosTip = false;
    }, 5000);
  }

  function clearRenewal(): void {
    if (renewalTimer !== null) {
      clearInterval(renewalTimer);
      renewalTimer = null;
    }
  }

  function stopAllMotion(): void {
    clearRenewal();
    leftX = 0;
    leftY = 0;
    leftDir = null;
    leftActive = false;
    rightX = 0;
    rightTurn = null;
    rightActive = false;
    if (activeDirection !== null) {
      activeDirection = null;
      void app.moveManual(null, nextManualSequence(), 'mobile');
    }
  }

  function resolveCombinedDirection(
    left: 'forward' | 'backward' | 'left' | 'right' | null,
    turn: 'turn_left' | 'turn_right' | null,
  ): ManualDirection | null {
    if (left === 'forward' && turn === 'turn_left') return 'forward+turn_left';
    if (left === 'forward' && turn === 'turn_right') return 'forward+turn_right';
    if (left === 'backward' && turn === 'turn_left') return 'backward+turn_left';
    if (left === 'backward' && turn === 'turn_right') return 'backward+turn_right';
    if (left !== null) return left;
    if (turn !== null) return turn;
    return null;
  }

  async function updateMotion(): Promise<void> {
    if (isJumping) return;
    const nextDir = resolveCombinedDirection(leftDir, rightTurn);
    if (nextDir === activeDirection) return;

    if (nextDir === null) {
      clearRenewal();
      activeDirection = null;
      void app.moveManual(null, nextManualSequence(), 'mobile');
      return;
    }

    activeDirection = nextDir;
    feedbackMessage = null;

    const result = await app.moveManual(nextDir, nextManualSequence(), 'mobile');
    if (result.blocked) {
      feedbackMessage = result.message ?? 'Mouvement bloqué.';
      stopAllMotion();
      return;
    }

    clearRenewal();
    renewalTimer = setInterval(async () => {
      if (activeDirection === null) return;
      const res = await app.moveManual(activeDirection, nextManualSequence(), 'mobile');
      if (res.blocked) {
        feedbackMessage = res.message ?? 'Mouvement bloqué.';
        stopAllMotion();
      }
    }, 180);
  }

  // --- Joystick gauche (2D : ZQSD) ---
  let leftStartX = 0;
  let leftStartY = 0;

  function onLeftPointerDown(event: PointerEvent): void {
    event.preventDefault();
    (event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);
    leftActive = true;
    leftStartX = event.clientX;
    leftStartY = event.clientY;
    leftX = 0;
    leftY = 0;
  }

  function onLeftPointerMove(event: PointerEvent): void {
    if (!leftActive) return;
    event.preventDefault();
    const rawDx = event.clientX - leftStartX;
    const rawDy = event.clientY - leftStartY;
    const dist = Math.hypot(rawDx, rawDy);
    let clampedX = rawDx;
    let clampedY = rawDy;
    if (dist > MAX_RADIUS) {
      const scale = MAX_RADIUS / dist;
      clampedX = rawDx * scale;
      clampedY = rawDy * scale;
    }
    leftX = clampedX;
    leftY = clampedY;

    let nextDir: 'forward' | 'backward' | 'left' | 'right' | null = null;
    if (dist > THRESHOLD) {
      if (Math.abs(clampedY) >= Math.abs(clampedX)) {
        nextDir = clampedY < 0 ? 'forward' : 'backward';
      } else {
        nextDir = clampedX < 0 ? 'left' : 'right';
      }
    }

    if (nextDir !== leftDir) {
      leftDir = nextDir;
      void updateMotion();
    }
  }

  function onLeftPointerUp(event: PointerEvent): void {
    event.preventDefault();
    leftActive = false;
    leftX = 0;
    leftY = 0;
    if (leftDir !== null) {
      leftDir = null;
      void updateMotion();
    }
  }

  // --- Joystick droit (horizontal : rotation) ---
  let rightStartX = 0;

  function onRightPointerDown(event: PointerEvent): void {
    event.preventDefault();
    (event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);
    rightActive = true;
    rightStartX = event.clientX;
    rightX = 0;
  }

  function onRightPointerMove(event: PointerEvent): void {
    if (!rightActive) return;
    event.preventDefault();
    const rawDx = event.clientX - rightStartX;
    const clampedDx = Math.max(-MAX_RADIUS, Math.min(MAX_RADIUS, rawDx));
    rightX = clampedDx;

    let nextTurn: 'turn_left' | 'turn_right' | null = null;
    if (clampedDx < -THRESHOLD) {
      nextTurn = 'turn_left';
    } else if (clampedDx > THRESHOLD) {
      nextTurn = 'turn_right';
    }

    if (nextTurn !== rightTurn) {
      rightTurn = nextTurn;
      void updateMotion();
    }
  }

  function onRightPointerUp(event: PointerEvent): void {
    event.preventDefault();
    rightActive = false;
    rightX = 0;
    if (rightTurn !== null) {
      rightTurn = null;
      void updateMotion();
    }
  }

  async function handleJump(): Promise<void> {
    if (isJumping) return;
    stopAllMotion();
    isJumping = true;
    feedbackMessage = null;
    try {
      const result = await app.jumpManual('mobile');
      if (result.blocked) {
        feedbackMessage = result.message ?? 'Le robot n’a pas pu sauter.';
      }
    } catch {
      feedbackMessage = 'Erreur lors du saut.';
    } finally {
      isJumping = false;
    }
  }

  onMount(() => {
    checkOrientation();
    updateFullscreenState();
    window.addEventListener('resize', checkOrientation);
    window.addEventListener('orientationchange', checkOrientation);
    window.addEventListener('fullscreenchange', updateFullscreenState);
    window.addEventListener('webkitfullscreenchange', updateFullscreenState);
    window.addEventListener('blur', stopAllMotion);
    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'hidden') stopAllMotion();
    });

    app.connect();
    void app.refreshStatus().then(() => {
      if (!app.status.manualActive) {
        void app.startManual();
      }
    });

    const pollLidar = async () => {
      while (lidarPollingActive) {
        if (viewMode === 'lidar') {
          try {
            const res = await api.getLidar();
            if (lidarPollingActive) {
              lidarVolume = res.volume;
            }
          } catch {
            if (lidarPollingActive) lidarVolume = null;
          }
        }
        await new Promise((r) => setTimeout(r, 400));
      }
    };
    void pollLidar();

    return () => {
      lidarPollingActive = false;
      if (tipTimer) clearTimeout(tipTimer);
      window.removeEventListener('resize', checkOrientation);
      window.removeEventListener('orientationchange', checkOrientation);
      window.removeEventListener('fullscreenchange', updateFullscreenState);
      window.removeEventListener('webkitfullscreenchange', updateFullscreenState);
      window.removeEventListener('blur', stopAllMotion);
      stopAllMotion();
    };
  });

  onDestroy(() => {
    stopAllMotion();
  });
</script>

{#if isPortrait}
  <!-- Verrouillage mode portrait -->
  <div class="portrait-guard" role="alert" aria-live="assertive">
    <div class="portrait-guard__box">
      <div class="portrait-guard__icon" aria-hidden="true">
        <Icon name="rotate" size={54} />
      </div>
      <h2 class="portrait-guard__title">Tournez votre téléphone</h2>
      <p class="portrait-guard__text">
        La manette mobile est spécialement conçue pour être utilisée en <strong>mode paysage</strong>.
      </p>
      <div class="portrait-guard__hint">
        Activez la rotation automatique si nécessaire.
      </div>
    </div>
  </div>
{:else}
  <!-- Manette mobile complète adaptée aux écrans iPhone en paysage -->
  <div class="mobile-gamepad" role="region" aria-label="Manette de pilotage mobile">
    <!-- Notification d'astuce plein écran iOS -->
    {#if showIosTip}
      <div class="ios-tip-toast" role="status">
        <span>💡 <strong>Astuce iPhone :</strong> Touchez <strong>Partager ⎋</strong> puis <strong>« Sur l'écran d'accueil ⊞ »</strong> pour cacher totalement l'URL et les onglets !</span>
        <button type="button" class="ios-tip-close" onclick={() => { showIosTip = false; }}>×</button>
      </div>
    {/if}

    <!-- Zone principale : 3 colonnes optimisées (Stick gauche, Scène centrale + Sauter, Stick droit) -->
    <main class="mobile-gamepad__arena">
      <!-- Colonne Joystick Gauche (Avancer / Reculer / Gauche / Droite) -->
      <section class="stick-zone stick-zone--left" aria-label="Contrôle déplacement ZQSD">
        <div class="stick-label stick-label--top" class:stick-label--active={leftDir === 'forward'}>
          ▲ AVANCER (Z)
        </div>

        <div class="stick-h-labels">
          <span class="stick-label" class:stick-label--active={leftDir === 'left'}>
            ◀ Q
          </span>
          <span class="stick-label" class:stick-label--active={leftDir === 'right'}>
            D ▶
          </span>
        </div>

        <div
          class="stick-base"
          class:stick-base--active={leftActive}
          onpointerdown={onLeftPointerDown}
          onpointermove={onLeftPointerMove}
          onpointerup={onLeftPointerUp}
          onpointercancel={onLeftPointerUp}
          role="slider"
          aria-label="Joystick déplacement ZQSD"
          aria-valuenow={leftDir ? 1 : 0}
          tabindex="0"
        >
          <div class="stick-axis stick-axis--vertical"></div>
          <div class="stick-axis stick-axis--horizontal"></div>
          <div
            class="stick-knob"
            class:stick-knob--active={leftActive}
            style="transform: translate3d({leftX}px, {leftY}px, 0);"
          >
            <div class="stick-knob__grip"></div>
          </div>
        </div>

        <div class="stick-label stick-label--bottom" class:stick-label--active={leftDir === 'backward'}>
          ▼ RECULER (S)
        </div>
      </section>

      <!-- Colonne Centrale (Scène LiDAR/Caméra + Barre d'outils + Bouton Sauter) -->
      <section class="center-stage" aria-label="Vue du robot">
        <!-- Barre de sélection supérieure : Bascule vue + Plein écran -->
        <div class="center-stage__view-toggle">
          <div class="toggle-group">
            <button
              type="button"
              class="view-btn"
              class:view-btn--active={viewMode === 'lidar'}
              onclick={() => { viewMode = 'lidar'; cameraFailed = false; }}
            >
              <Icon name="radar" size={13} />
              <span>LiDAR 3D</span>
            </button>
            <button
              type="button"
              class="view-btn"
              class:view-btn--active={viewMode === 'camera'}
              onclick={() => { viewMode = 'camera'; cameraFailed = false; }}
            >
              <Icon name="camera" size={13} />
              <span>Caméra</span>
            </button>
          </div>

          <!-- Bouton Plein écran pour cacher les barres web -->
          <button
            type="button"
            class="fullscreen-btn"
            class:fullscreen-btn--active={isFullscreen}
            onclick={toggleFullscreen}
            title={isFullscreen ? 'Quitter le plein écran' : 'Passer en plein écran'}
          >
            <Icon name={isFullscreen ? 'compress' : 'expand'} size={13} />
            <span>{isFullscreen ? 'Réduire' : 'Plein écran'}</span>
          </button>
        </div>

        <!-- Rendu LiDAR ou Caméra : flex 1 pour s'adapter à la hauteur -->
        <div class="center-stage__viewport">
          {#if viewMode === 'lidar'}
            <div class="center-stage__lidar-wrap">
              <LidarScene
                volume={lidarVolume}
                walking={activeDirection !== null}
                interactive={false}
                posture={app.status.posture}
              />
            </div>
          {:else}
            <div class="center-stage__camera-wrap">
              {#if cameraFailed}
                <div class="camera-fallback">
                  <Icon name="camera" size={28} />
                  <p>Caméra non disponible</p>
                </div>
              {:else}
                <img
                  class="camera-stream"
                  src={cameraUrl}
                  alt="Flux direct caméra Go2"
                  onerror={() => (cameraFailed = true)}
                />
              {/if}
            </div>
          {/if}

          {#if app.status.manualSource === 'keyboard'}
            <div class="arbitration-badge" role="status">
              💻 Clavier PC actif
            </div>
          {/if}

          {#if feedbackMessage}
            <div class="feedback-badge" role="status">
              {feedbackMessage}
            </div>
          {/if}
        </div>

        <!-- Bouton d'action : Sauter -->
        <div class="center-stage__actions">
          <button
            type="button"
            class="jump-button"
            class:jump-button--active={isJumping}
            disabled={isJumping}
            onclick={handleJump}
            title="Faire sauter le robot"
          >
            <Icon name="paw" size={16} />
            <span>{isJumping ? 'Saut...' : 'SAUTER'}</span>
          </button>
        </div>
      </section>

      <!-- Colonne Joystick Droit (Rotation Gauche / Droite) -->
      <section class="stick-zone stick-zone--right" aria-label="Contrôle rotation">
        <div class="stick-h-labels">
          <span class="stick-label" class:stick-label--active={rightTurn === 'turn_left'}>
            ↺ PIVOT G.
          </span>
          <span class="stick-label" class:stick-label--active={rightTurn === 'turn_right'}>
            PIVOT D. ↻
          </span>
        </div>

        <div
          class="stick-base"
          class:stick-base--active={rightActive}
          onpointerdown={onRightPointerDown}
          onpointermove={onRightPointerMove}
          onpointerup={onRightPointerUp}
          onpointercancel={onRightPointerUp}
          role="slider"
          aria-label="Joystick rotation"
          aria-valuenow={rightTurn === 'turn_left' ? -1 : rightTurn === 'turn_right' ? 1 : 0}
          tabindex="0"
        >
          <div class="stick-axis stick-axis--horizontal"></div>
          <div
            class="stick-knob"
            class:stick-knob--active={rightActive}
            style="transform: translate3d({rightX}px, 0, 0);"
          >
            <div class="stick-knob__grip"></div>
          </div>
        </div>

        <div class="stick-hint">
          {rightTurn === 'turn_left' ? 'Rotation G' : rightTurn === 'turn_right' ? 'Rotation D' : 'Rotation'}
        </div>
      </section>
    </main>
  </div>
{/if}

<style>
  /* Verrouillage portrait */
  .portrait-guard {
    position: fixed;
    inset: 0;
    z-index: 9999;
    display: flex;
    align-items: center;
    justify-content: center;
    background: #0f172a;
    color: #ffffff;
    padding: 24px;
    text-align: center;
  }

  .portrait-guard__box {
    display: flex;
    flex-direction: column;
    align-items: center;
    max-width: 320px;
  }

  .portrait-guard__icon {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 80px;
    height: 80px;
    border-radius: 50%;
    background: rgba(59, 130, 246, 0.15);
    color: #60a5fa;
    margin-bottom: 18px;
    animation: pulseIcon 2s infinite ease-in-out;
  }

  @keyframes pulseIcon {
    0%, 100% {
      transform: scale(1) rotate(0deg);
    }
    50% {
      transform: scale(1.08) rotate(90deg);
    }
  }

  .portrait-guard__title {
    margin: 0 0 10px;
    font-size: 1.3rem;
    font-weight: 700;
    color: #f8fafc;
  }

  .portrait-guard__text {
    margin: 0 0 16px;
    font-size: 0.9rem;
    color: #94a3b8;
    line-height: 1.5;
  }

  .portrait-guard__hint {
    font-size: 0.76rem;
    color: #64748b;
    background: rgba(255, 255, 255, 0.05);
    padding: 6px 12px;
    border-radius: 999px;
  }

  /* Toast astuce plein écran iOS */
  .ios-tip-toast {
    position: absolute;
    top: 6px;
    left: 50%;
    transform: translateX(-50%);
    background: rgba(30, 41, 59, 0.95);
    color: #e2e8f0;
    border: 1px solid #3b82f6;
    padding: 6px 14px;
    border-radius: 999px;
    font-size: 0.74rem;
    z-index: 5000;
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.5);
    display: flex;
    align-items: center;
    gap: 8px;
    animation: slideDown 0.2s ease-out;
    max-width: 90%;
    white-space: nowrap;
  }

  @keyframes slideDown {
    from {
      opacity: 0;
      transform: translate(-50%, -10px);
    }
    to {
      opacity: 1;
      transform: translate(-50%, 0);
    }
  }

  .ios-tip-close {
    border: none;
    background: transparent;
    color: #94a3b8;
    font-size: 1rem;
    cursor: pointer;
    padding: 0 4px;
  }

  /* Manette complète paysage avec support Safe Area iOS */
  .mobile-gamepad {
    position: fixed;
    inset: 0;
    z-index: 2000;
    display: flex;
    background: #0a0f1d;
    color: #f1f5f9;
    overflow: hidden;
    user-select: none;
    touch-action: none;
    height: 100dvh;
    height: 100vh;
    padding-top: max(4px, env(safe-area-inset-top));
    padding-bottom: max(6px, env(safe-area-inset-bottom));
    padding-left: max(10px, env(safe-area-inset-left));
    padding-right: max(10px, env(safe-area-inset-right));
    box-sizing: border-box;
  }

  /* Grille 3 colonnes ajustée pour iPhone */
  .mobile-gamepad__arena {
    flex: 1;
    display: grid;
    grid-template-columns: 140px 1fr 140px;
    gap: 8px;
    padding: 2px 4px;
    overflow: hidden;
    height: 100%;
    min-height: 0;
    box-sizing: border-box;
  }

  /* Colonnes joysticks */
  .stick-zone {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 4px;
    position: relative;
    touch-action: none;
  }

  .stick-label {
    font-size: 0.68rem;
    font-weight: 700;
    letter-spacing: 0.03em;
    color: #64748b;
    transition: color 0.1s ease;
  }

  .stick-label--active {
    color: #60a5fa;
    text-shadow: 0 0 6px rgba(96, 165, 250, 0.6);
  }

  .stick-h-labels {
    display: flex;
    justify-content: space-between;
    width: 125px;
    padding: 0 2px;
  }

  .stick-hint {
    font-size: 0.68rem;
    color: #64748b;
  }

  .stick-base {
    position: relative;
    width: 108px;
    height: 108px;
    border-radius: 50%;
    background: radial-gradient(circle, rgba(30, 41, 59, 0.8) 0%, rgba(15, 23, 42, 0.95) 100%);
    border: 2px solid rgba(255, 255, 255, 0.12);
    box-shadow: inset 0 3px 10px rgba(0, 0, 0, 0.6), 0 3px 10px rgba(0, 0, 0, 0.4);
    display: grid;
    place-items: center;
    cursor: grab;
    touch-action: none;
    outline: none;
    transition: border-color 0.15s;
  }

  .stick-base--active {
    border-color: #3b82f6;
    box-shadow: inset 0 3px 10px rgba(0, 0, 0, 0.6), 0 0 14px rgba(59, 130, 246, 0.35);
  }

  .stick-axis {
    position: absolute;
    background: rgba(255, 255, 255, 0.08);
    pointer-events: none;
  }

  .stick-axis--vertical {
    width: 3px;
    height: 74px;
    border-radius: 2px;
  }

  .stick-axis--horizontal {
    width: 74px;
    height: 3px;
    border-radius: 2px;
  }

  .stick-knob {
    position: absolute;
    width: 44px;
    height: 44px;
    border-radius: 50%;
    background: linear-gradient(145deg, #3b82f6, #1d4ed8);
    border: 2px solid rgba(255, 255, 255, 0.4);
    box-shadow: 0 3px 8px rgba(0, 0, 0, 0.5), inset 0 2px 3px rgba(255, 255, 255, 0.3);
    display: grid;
    place-items: center;
    pointer-events: none;
    will-change: transform;
    transition: transform 0.04s ease-out;
  }

  .stick-knob--active {
    background: linear-gradient(145deg, #60a5fa, #2563eb);
    box-shadow: 0 4px 12px rgba(37, 99, 235, 0.6), inset 0 2px 3px rgba(255, 255, 255, 0.5);
  }

  .stick-knob__grip {
    width: 16px;
    height: 16px;
    border-radius: 50%;
    background: rgba(255, 255, 255, 0.2);
    border: 1px solid rgba(255, 255, 255, 0.3);
  }

  /* Colonne centrale */
  .center-stage {
    display: flex;
    flex-direction: column;
    gap: 4px;
    height: 100%;
    min-height: 0;
  }

  .center-stage__view-toggle {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    flex: none;
    height: 26px;
  }

  .toggle-group {
    display: flex;
    gap: 6px;
  }

  .view-btn,
  .fullscreen-btn {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    padding: 3px 10px;
    border-radius: 999px;
    border: 1px solid rgba(255, 255, 255, 0.12);
    background: rgba(30, 41, 59, 0.6);
    color: #94a3b8;
    font-size: 0.7rem;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.15s;
    height: 24px;
  }

  .view-btn--active {
    background: #2563eb;
    border-color: #3b82f6;
    color: #ffffff;
    box-shadow: 0 2px 6px rgba(37, 99, 235, 0.35);
  }

  .fullscreen-btn {
    background: rgba(255, 255, 255, 0.06);
    border-color: rgba(255, 255, 255, 0.18);
    color: #cbd5e1;
  }

  .fullscreen-btn:hover,
  .fullscreen-btn--active {
    background: rgba(59, 130, 246, 0.2);
    border-color: #3b82f6;
    color: #60a5fa;
  }

  .center-stage__viewport {
    position: relative;
    flex: 1 1 0;
    min-height: 0;
    border-radius: 10px;
    background: #030712;
    border: 1px solid rgba(255, 255, 255, 0.1);
    overflow: hidden;
  }

  .center-stage__lidar-wrap,
  .center-stage__camera-wrap {
    width: 100%;
    height: 100%;
    position: relative;
  }

  .camera-stream {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }

  .camera-fallback {
    width: 100%;
    height: 100%;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    color: #64748b;
    gap: 6px;
    font-size: 0.8rem;
  }

  .arbitration-badge {
    position: absolute;
    top: 6px;
    left: 50%;
    transform: translateX(-50%);
    background: rgba(239, 68, 68, 0.9);
    color: #ffffff;
    font-size: 0.72rem;
    font-weight: 700;
    padding: 3px 10px;
    border-radius: 999px;
    backdrop-filter: blur(4px);
    box-shadow: 0 3px 8px rgba(0, 0, 0, 0.35);
    z-index: 10;
    animation: blink 1.5s infinite;
  }

  @keyframes blink {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.6; }
  }

  .feedback-badge {
    position: absolute;
    bottom: 6px;
    left: 50%;
    transform: translateX(-50%);
    background: rgba(239, 68, 68, 0.85);
    color: #ffffff;
    font-size: 0.72rem;
    font-weight: 600;
    padding: 3px 10px;
    border-radius: 999px;
    backdrop-filter: blur(4px);
    box-shadow: 0 3px 6px rgba(0, 0, 0, 0.3);
  }

  /* Bouton d'action : Sauter */
  .center-stage__actions {
    flex: none;
    display: flex;
    justify-content: center;
    padding-top: 2px;
  }

  .jump-button {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 5px;
    width: 118px;
    height: 32px;
    border: none;
    border-radius: 999px;
    background: linear-gradient(180deg, #ec4899, #be185d);
    color: #ffffff;
    font-size: 0.76rem;
    font-weight: 750;
    letter-spacing: 0.04em;
    cursor: pointer;
    box-shadow: 0 3px 10px rgba(219, 39, 119, 0.4);
    transition: transform 0.08s ease, filter 0.15s ease;
  }

  .jump-button:active,
  .jump-button--active {
    transform: translateY(2px) scale(0.98);
    filter: brightness(1.15);
    box-shadow: 0 1px 6px rgba(219, 39, 119, 0.6);
  }

  .jump-button:disabled {
    opacity: 0.65;
    cursor: not-allowed;
  }
</style>
