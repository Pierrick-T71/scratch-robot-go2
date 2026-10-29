<script lang="ts">
  /**
   * Manette mobile en mode paysage pour piloter le Go2 Pro.
   *
   * Optimisée pour smartphones (iPhone, Android) en paysage :
   *  - Utilisation de 100dvh et des safe-area insets pour éviter tout débordement
   *  - Joystick gauche 2D (ZQSD) et joystick droit (rotation)
   *  - Boutons d'action rapides sous les deux joysticks avec uniquement les logos
   *  - Scène 3D robot active qui se déplace en simulation sur la grille comme sur le site
   *  - Bascule Robot 3D / LiDAR / Caméra et bouton plein écran
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

  // Recentrage simulation
  let resetTrigger = $state(0);
  let isResetting = $state(false);
  let lidarSceneRef = $state<ReturnType<typeof LidarScene> | undefined>();

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
  let runningAction = $state<string | null>(null);
  let actionTimeout: ReturnType<typeof setTimeout> | null = null;
  let feedbackMessage = $state<string | null>(null);

  let renewalTimer: ReturnType<typeof setInterval> | null = null;
  let lidarPollingActive = true;

  // Rayon et seuil adaptés aux écrans compacts en paysage
  const MAX_RADIUS = 36;
  const THRESHOLD = 12;
  const cameraUrl = `${SERVICE_URL}/api/robot/camera`;

  // Posture et geste effectifs pour le modèle 3D
  const effectivePosture = $derived(
    runningAction === 'heart'
      ? 'sit'
      : runningAction === 'salute' ||
          runningAction === 'stretch' ||
          runningAction === 'jump'
        ? 'stand'
        : (app.status.posture ?? 'stand'),
  );

  const effectiveAction = $derived(
    runningAction === 'salute' ||
      runningAction === 'heart' ||
      runningAction === 'stretch' ||
      runningAction === 'jump'
      ? runningAction
      : null,
  );

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

  function handleResetSimulation(): void {
    resetTrigger += 1;
    isResetting = true;
    setTimeout(() => {
      isResetting = false;
    }, 500);
    lidarSceneRef?.recentrer?.();
    void app.resetSimulation();
  }

  function clearRenewal(): void {
    if (renewalTimer !== null) {
      clearInterval(renewalTimer);
      renewalTimer = null;
    }
  }

  function cancelRunningAction(): void {
    if (actionTimeout !== null) {
      clearTimeout(actionTimeout);
      actionTimeout = null;
    }
    isJumping = false;
    runningAction = null;
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
    const nextDir = resolveCombinedDirection(leftDir, rightTurn);
    if (nextDir === activeDirection) return;

    if (nextDir === null) {
      clearRenewal();
      activeDirection = null;
      void app.moveManual(null, nextManualSequence(), 'mobile');
      return;
    }

    // Le déplacement manuel annule immédiatement tout geste ou posture assise/couchée
    cancelRunningAction();
    if (app.status.posture !== 'stand') {
      app.status = { ...app.status, posture: 'stand' };
      void app.actionManual('stand', 'mobile');
    }

    activeDirection = nextDir;
    feedbackMessage = null;

    const result = await app.moveManual(nextDir, nextManualSequence(), 'mobile');
    if (result.blocked) {
      feedbackMessage = result.message ?? 'Mouvement bloqué.';
      stopAllMotion();
      return;
    }

    // Mise à jour de la position simulée
    void app.refreshStatus();

    clearRenewal();
    renewalTimer = setInterval(async () => {
      if (activeDirection === null) return;
      const res = await app.moveManual(activeDirection, nextManualSequence(), 'mobile');
      if (res.blocked) {
        feedbackMessage = res.message ?? 'Mouvement bloqué.';
        stopAllMotion();
      } else {
        // En simulation, rafraîchir le statut met à jour position et yawRad pour faire bouger le robot 3D
        void app.refreshStatus();
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

  // --- Exécution des actions et postures (boutons sous les joysticks) ---
  async function triggerAction(actionName: string): Promise<void> {
    // Annuler immédiatement l'action précédente en cours (timeout, saut ou geste)
    cancelRunningAction();
    stopAllMotion();
    feedbackMessage = null;

    // Déterminer la nouvelle posture selon l'action : toute action remplace la précédente
    let targetPosture: 'stand' | 'sit' | 'lie_down' | 'balance' = 'stand';
    if (actionName === 'sit' || actionName === 'heart') {
      targetPosture = 'sit';
    } else if (actionName === 'lie_down') {
      targetPosture = 'lie_down';
    } else if (actionName === 'balance') {
      targetPosture = 'balance';
    } else {
      // stand, jump, salute, stretch -> posture debout
      targetPosture = 'stand';
    }

    // Appliquer immédiatement la posture cible dans l'état global
    app.status = { ...app.status, posture: targetPosture };

    if (actionName === 'jump') {
      isJumping = true;
      runningAction = 'jump';
      actionTimeout = setTimeout(() => {
        isJumping = false;
        runningAction = null;
        actionTimeout = null;
      }, 1500);

      try {
        const result = await app.jumpManual('mobile');
        if (result.blocked) {
          feedbackMessage = result.message ?? 'Le robot n’a pas pu sauter.';
        }
      } catch {
        feedbackMessage = 'Erreur lors du saut.';
      }
      return;
    }

    // Gestes avec animation temporaire (salut, coeur, étirement)
    const isGesture = ['salute', 'heart', 'stretch'].includes(actionName);
    if (isGesture) {
      runningAction = actionName;
      const duration =
        actionName === 'stretch' || actionName === 'salute'
          ? 3000
          : 2800; // 'heart'
      actionTimeout = setTimeout(() => {
        runningAction = null;
        actionTimeout = null;
      }, duration);
    } else {
      // Pour les postures ('stand', 'sit', 'lie_down', 'balance'),
      // aucune temporisation bloquante n'est conservée.
      runningAction = null;
    }

    try {
      const result = await app.actionManual(actionName, 'mobile');
      if (result.blocked && result.message) {
        feedbackMessage = result.message;
      }
    } catch {
      feedbackMessage = 'Erreur lors de l’action.';
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
      cancelRunningAction();
      window.removeEventListener('resize', checkOrientation);
      window.removeEventListener('orientationchange', checkOrientation);
      window.removeEventListener('fullscreenchange', updateFullscreenState);
      window.removeEventListener('webkitfullscreenchange', updateFullscreenState);
      window.removeEventListener('blur', stopAllMotion);
      stopAllMotion();
    };
  });

  onDestroy(() => {
    cancelRunningAction();
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
  <!-- Manette mobile complète 100% responsive en mode paysage -->
  <div class="mobile-gamepad" role="region" aria-label="Manette de pilotage mobile">
    <!-- Notification astuce plein écran iOS -->
    {#if showIosTip}
      <div class="ios-tip-toast" role="status">
        <span>💡 <strong>Astuce iPhone :</strong> Touchez <strong>Partager ⎋</strong> puis <strong>« Sur l'écran d'accueil ⊞ »</strong> pour masquer la barre web !</span>
        <button type="button" class="ios-tip-close" onclick={() => { showIosTip = false; }}>×</button>
      </div>
    {/if}

    <main class="mobile-gamepad__arena">
      <!-- Colonne Gauche : Joystick Déplacement ZQSD + Boutons Posture sous le stick -->
      <section class="stick-zone stick-zone--left" aria-label="Déplacement">
        <div class="stick-header">
          <span class="stick-badge" class:stick-badge--active={leftDir !== null}>
            {#if leftDir === 'forward'}▲ AVANCER
            {:else if leftDir === 'backward'}▼ RECULER
            {:else if leftDir === 'left'}◀ GAUCHE
            {:else if leftDir === 'right'}DROITE ▶
            {:else}ZQSD{/if}
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

        <!-- 4 boutons d'action sous le joystick gauche avec uniquement les logos -->
        <div class="action-pad" aria-label="Postures du robot">
          <button
            type="button"
            class="action-btn"
            class:action-btn--active={effectivePosture === 'stand' && runningAction === null}
            onclick={() => triggerAction('stand')}
            title="Se mettre debout"
            aria-label="Se mettre debout"
          >
            <Icon name="stand" size={19} />
          </button>

          <button
            type="button"
            class="action-btn"
            class:action-btn--active={effectivePosture === 'sit' && runningAction === null}
            onclick={() => triggerAction('sit')}
            title="S'asseoir"
            aria-label="S'asseoir"
          >
            <Icon name="sit" size={19} />
          </button>

          <button
            type="button"
            class="action-btn"
            class:action-btn--active={effectivePosture === 'lie_down' && runningAction === null}
            onclick={() => triggerAction('lie_down')}
            title="Se coucher"
            aria-label="Se coucher"
          >
            <Icon name="moon" size={19} />
          </button>

          <button
            type="button"
            class="action-btn"
            class:action-btn--active={effectivePosture === 'balance' && runningAction === null}
            onclick={() => triggerAction('balance')}
            title="Faire le beau"
            aria-label="Faire le beau"
          >
            <Icon name="balance" size={19} />
          </button>
        </div>
      </section>

      <!-- Colonne Centrale : Scène 3D Robot / LiDAR / Caméra avec mouvement complet en simulation -->
      <section class="center-stage" aria-label="Vue du robot">
        <!-- Barre supérieure : Bascule vue, état connexion, bouton plein écran -->
        <header class="center-stage__bar">
          <div class="toggle-group">
            <button
              type="button"
              class="view-btn"
              class:view-btn--active={viewMode === 'lidar'}
              onclick={() => { viewMode = 'lidar'; cameraFailed = false; }}
            >
              <Icon name="radar" size={13} />
              <span>Scène 3D</span>
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

          <!-- Indicateur d'état -->
          <div class="status-indicator">
            <span class="status-dot" class:status-dot--connected={app.status.connected}></span>
            <span class="status-text">{app.status.connected ? 'Connecté' : 'Simulation'}</span>
            {#if app.status.batteryPercent !== null}
              <span class="status-battery">{Math.round(app.status.batteryPercent)}%</span>
            {/if}
          </div>

          <!-- Plein écran -->
          <button
            type="button"
            class="fullscreen-btn"
            class:fullscreen-btn--active={isFullscreen}
            onclick={toggleFullscreen}
            title={isFullscreen ? 'Quitter le plein écran' : 'Plein écran'}
            aria-label={isFullscreen ? 'Quitter le plein écran' : 'Plein écran'}
          >
            <Icon name={isFullscreen ? 'compress' : 'expand'} size={13} />
          </button>
        </header>

        <!-- Viewport 3D ou Caméra : le robot bouge en temps réel sur la carte comme sur le site -->
        <div class="center-stage__viewport">
          {#if viewMode === 'lidar'}
            <div class="center-stage__scene-wrap">
              <LidarScene
                bind:this={lidarSceneRef}
                volume={lidarVolume}
                walking={activeDirection !== null}
                interactive={true}
                posture={effectivePosture}
                action={effectiveAction}
                position={app.status.position}
                yawRad={app.status.yawRad}
                resetTrigger={resetTrigger + app.resetSimulationTrigger}
              />

              <!-- Bouton pour recentrer le robot au milieu de la carte -->
              <button
                type="button"
                class="recenter-btn"
                class:recenter-btn--spinning={isResetting}
                onclick={handleResetSimulation}
                title="Recentrer le robot au centre de la carte"
                aria-label="Recentrer le robot"
              >
                <Icon name="refresh" size={16} />
              </button>
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
      </section>

      <!-- Colonne Droite : Joystick Rotation + Boutons d'Action sous le stick -->
      <section class="stick-zone stick-zone--right" aria-label="Rotation">
        <div class="stick-header">
          <span class="stick-badge" class:stick-badge--active={rightTurn !== null}>
            {#if rightTurn === 'turn_left'}↺ PIVOT G.
            {:else if rightTurn === 'turn_right'}PIVOT D. ↻
            {:else}ROTATION{/if}
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

        <!-- 4 boutons d'action sous le joystick droit avec uniquement les logos -->
        <div class="action-pad" aria-label="Actions spéciales">
          <button
            type="button"
            class="action-btn action-btn--jump"
            class:action-btn--active={isJumping || runningAction === 'jump'}
            onclick={() => triggerAction('jump')}
            title="Sauter"
            aria-label="Sauter"
          >
            <Icon name="paw" size={19} />
          </button>

          <button
            type="button"
            class="action-btn"
            class:action-btn--active={runningAction === 'salute'}
            onclick={() => triggerAction('salute')}
            title="Saluer"
            aria-label="Saluer"
          >
            <Icon name="hand" size={19} />
          </button>

          <button
            type="button"
            class="action-btn action-btn--heart"
            class:action-btn--active={runningAction === 'heart'}
            onclick={() => triggerAction('heart')}
            title="Faire un cœur"
            aria-label="Faire un cœur"
          >
            <Icon name="heart" size={19} />
          </button>

          <button
            type="button"
            class="action-btn"
            class:action-btn--active={runningAction === 'stretch'}
            onclick={() => triggerAction('stretch')}
            title="S'étirer"
            aria-label="S'étirer"
          >
            <Icon name="stretch" size={19} />
          </button>
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
    background: #080c16;
    color: #f1f5f9;
    overflow: hidden;
    user-select: none;
    touch-action: none;
    height: 100dvh;
    height: 100vh;
    padding-top: max(4px, env(safe-area-inset-top));
    padding-bottom: max(6px, env(safe-area-inset-bottom));
    padding-left: max(8px, env(safe-area-inset-left));
    padding-right: max(8px, env(safe-area-inset-right));
    box-sizing: border-box;
  }

  /* Grille 3 colonnes ultra-responsive */
  .mobile-gamepad__arena {
    flex: 1;
    display: grid;
    grid-template-columns: clamp(100px, 20vw, 140px) 1fr clamp(100px, 20vw, 140px);
    gap: clamp(6px, 1.5vw, 12px);
    padding: 2px 4px;
    overflow: hidden;
    height: 100%;
    min-height: 0;
    box-sizing: border-box;
  }

  /* Colonnes latérales joysticks + boutons d'action */
  .stick-zone {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: space-evenly;
    height: 100%;
    min-height: 0;
    position: relative;
    touch-action: none;
  }

  .stick-header {
    flex: none;
    display: flex;
    align-items: center;
    justify-content: center;
    height: 22px;
  }

  .stick-badge {
    font-size: 0.65rem;
    font-weight: 750;
    letter-spacing: 0.04em;
    color: #64748b;
    padding: 2px 8px;
    border-radius: 999px;
    background: rgba(255, 255, 255, 0.04);
    border: 1px solid rgba(255, 255, 255, 0.07);
    transition: all 0.1s ease;
    white-space: nowrap;
  }

  .stick-badge--active {
    color: #60a5fa;
    border-color: rgba(96, 165, 250, 0.4);
    background: rgba(59, 130, 246, 0.15);
    text-shadow: 0 0 6px rgba(96, 165, 250, 0.6);
  }

  /* Base du joystick */
  .stick-base {
    position: relative;
    width: clamp(84px, 21vh, 106px);
    height: clamp(84px, 21vh, 106px);
    border-radius: 50%;
    background: radial-gradient(circle, rgba(30, 41, 59, 0.85) 0%, rgba(15, 23, 42, 0.98) 100%);
    border: 2px solid rgba(255, 255, 255, 0.14);
    box-shadow: inset 0 3px 10px rgba(0, 0, 0, 0.6), 0 4px 12px rgba(0, 0, 0, 0.4);
    display: grid;
    place-items: center;
    cursor: grab;
    touch-action: none;
    outline: none;
    flex: none;
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
    height: 70%;
    border-radius: 2px;
  }

  .stick-axis--horizontal {
    width: 70%;
    height: 3px;
    border-radius: 2px;
  }

  .stick-knob {
    position: absolute;
    width: clamp(38px, 9vh, 44px);
    height: clamp(38px, 9vh, 44px);
    border-radius: 50%;
    background: linear-gradient(145deg, #3b82f6, #1d4ed8);
    border: 2px solid rgba(255, 255, 255, 0.45);
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
    width: 14px;
    height: 14px;
    border-radius: 50%;
    background: rgba(255, 255, 255, 0.25);
    border: 1px solid rgba(255, 255, 255, 0.35);
  }

  /* Pavé d'action sous les joysticks (2x2 avec uniquement les logos) */
  .action-pad {
    flex: none;
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: clamp(5px, 1.2vh, 8px);
    width: clamp(80px, 18vh, 98px);
    touch-action: manipulation;
  }

  .action-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    aspect-ratio: 1 / 1;
    width: 100%;
    border-radius: 50%;
    border: 1.5px solid rgba(255, 255, 255, 0.16);
    background: linear-gradient(145deg, #1e293b, #0f172a);
    color: #94a3b8;
    box-shadow:
      inset 0 1px 0 rgba(255, 255, 255, 0.1),
      0 3px 8px rgba(0, 0, 0, 0.45);
    cursor: pointer;
    touch-action: manipulation;
    transition: transform 0.08s ease, background 0.12s ease, border-color 0.12s ease, color 0.12s ease, box-shadow 0.12s ease;
  }

  .action-btn:active {
    transform: scale(0.92);
  }

  .action-btn--active {
    background: linear-gradient(145deg, #3b82f6, #1d4ed8);
    border-color: #60a5fa;
    color: #ffffff;
    box-shadow:
      inset 0 1px 0 rgba(255, 255, 255, 0.3),
      0 0 14px rgba(59, 130, 246, 0.55);
  }

  .action-btn--jump.action-btn--active {
    background: linear-gradient(145deg, #ec4899, #be185d);
    border-color: #f472b6;
    box-shadow:
      inset 0 1px 0 rgba(255, 255, 255, 0.3),
      0 0 14px rgba(236, 72, 153, 0.55);
  }

  .action-btn--heart.action-btn--active {
    background: linear-gradient(145deg, #f43f5e, #be123c);
    border-color: #fb7185;
    box-shadow:
      inset 0 1px 0 rgba(255, 255, 255, 0.3),
      0 0 14px rgba(244, 63, 94, 0.55);
  }

  /* Colonne centrale */
  .center-stage {
    display: flex;
    flex-direction: column;
    gap: 4px;
    height: 100%;
    min-height: 0;
  }

  .center-stage__bar {
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

  .status-indicator {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 0.68rem;
    color: #94a3b8;
    font-weight: 600;
  }

  .status-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: #eab308;
  }

  .status-dot--connected {
    background: #22c55e;
    box-shadow: 0 0 6px rgba(34, 197, 94, 0.6);
  }

  .status-battery {
    padding: 1px 5px;
    background: rgba(255, 255, 255, 0.08);
    border-radius: 4px;
    font-size: 0.65rem;
    color: #cbd5e1;
  }

  .fullscreen-btn {
    background: rgba(255, 255, 255, 0.06);
    border-color: rgba(255, 255, 255, 0.18);
    color: #cbd5e1;
    padding: 3px 8px;
  }

  .fullscreen-btn:hover,
  .fullscreen-btn--active {
    background: rgba(59, 130, 246, 0.2);
    border-color: #3b82f6;
    color: #60a5fa;
  }

  /* Viewport central */
  .center-stage__viewport {
    position: relative;
    flex: 1 1 0;
    min-height: 0;
    border-radius: 12px;
    background: #030712;
    border: 1px solid rgba(255, 255, 255, 0.1);
    overflow: hidden;
  }

  .center-stage__scene-wrap,
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

  /* Bouton de recentrage au centre de la carte */
  .recenter-btn {
    position: absolute;
    bottom: 8px;
    right: 8px;
    z-index: 10;
    width: 32px;
    height: 32px;
    border-radius: 50%;
    border: 1px solid rgba(255, 255, 255, 0.2);
    background: rgba(15, 23, 42, 0.75);
    color: #cbd5e1;
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    backdrop-filter: blur(4px);
    transition: transform 0.15s ease, background 0.15s ease, color 0.15s ease;
  }

  .recenter-btn:hover {
    background: rgba(30, 41, 59, 0.9);
    color: #ffffff;
  }

  .recenter-btn:active {
    transform: scale(0.92);
  }

  .recenter-btn--spinning :global(svg) {
    animation: spin 0.5s ease-in-out;
  }

  @keyframes spin {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
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
    bottom: 8px;
    left: 50%;
    transform: translateX(-50%);
    background: rgba(239, 68, 68, 0.88);
    color: #ffffff;
    font-size: 0.72rem;
    font-weight: 600;
    padding: 3px 10px;
    border-radius: 999px;
    backdrop-filter: blur(4px);
    box-shadow: 0 3px 6px rgba(0, 0, 0, 0.3);
    z-index: 10;
  }
</style>
