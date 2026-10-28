<script lang="ts">
  /**
   * Go2 Play — écran principal.
   *
   * Trois zones :
   *  1. la barre du haut     (PlayHeader) : identité, mode manuel / Arrêter / Sauvegarder ;
   *  2. la bibliothèque      (BlockLibrary) et « Mon Programme » (ProgramTimeline) ;
   *  3. la vue du robot      (RobotStage), à droite, sur toute la hauteur.
   *
   * Le programme se lance avec le drapeau de « Mon Programme ». Le mode manuel
   * remplace l'ancien bouton « Lancer » de la barre du haut.
   *
   * L'interface n'accède jamais au robot : tout passe par `app` (lib/stores),
   * qui parle au service. Les douze blocs sont traduits en `Program` par
   * `lib/play/blocks` — la même structure que le service connaît déjà.
   */
  import { onMount, untrack } from 'svelte';
  import PlayHeader from './components/play/PlayHeader.svelte';
  import BlockLibrary from './components/play/BlockLibrary.svelte';
  import ProgramTimeline from './components/play/ProgramTimeline.svelte';
  import BlockedPopup from './components/play/BlockedPopup.svelte';
import StandbyOverlay from './components/play/StandbyOverlay.svelte';
  import MobileGamepad from './components/play/MobileGamepad.svelte';
  import ManualPanel from './components/play/ManualPanel.svelte';
  import RobotStage from './components/play/RobotStage.svelte';
  import RobotConnect from './components/RobotConnect.svelte';
  import SettingsPanel from './components/SettingsPanel.svelte';
  import HelpModal from './components/HelpModal.svelte';
  import ModeSwitch from './components/ModeSwitch.svelte';
  import { app } from './lib/stores/app.svelte';
  import {
    createBlock,
    toProgram,
    type PlayBlock,
    type PlayBlockKind,
  } from './lib/play/blocks';
  import {
    clearSavedBlocks,
    downloadProgramJson,
    loadBlocks,
    parseBlocksFromJson,
    PlayStorageError,
    saveBlocks,
  } from './lib/play/storage';

  let blocks = $state<PlayBlock[]>([]);

  let showHelp = $state(false);
  let showMode = $state(false);
  let showSettings = $state(false);
  let showRobot = $state(false);
  let showSafetyOffConfirm = $state(false);
  let manualMode = $state(false);
  let fileInputEl = $state<HTMLInputElement | undefined>();
  let isRemoteMode = $state(
    typeof window !== 'undefined' &&
      (window.location.search.includes('remote') || window.location.hash.includes('remote')),
  );

  /** Ce que voit l'enfant EST ce qui part : une seule source de vérité. */
  const program = $derived(toProgram(blocks));

  /** Index du bloc en cours d'exécution (null hors exécution). */
  const runningIndex = $derived(
    app.steps.find((step) => step.state === 'running')?.index ?? null,
  );

  /** Le bloc en cours est-il un déplacement ? Alors le robot marche. */
  const runningKind = $derived(
    runningIndex === null ? null : (blocks[runningIndex]?.kind ?? null),
  );

  const isManualMoving = $derived(
    Boolean(
      manualMode &&
        ((app.manualMotion && app.manualMotion.direction !== null) ||
          app.status.manualDirection ||
          app.status.state === 'moving'),
    ),
  );

  const isManualSprinting = $derived(
    Boolean(
      manualMode &&
        ((app.manualMotion && app.manualMotion.sprint) ||
          app.status.manualSprint),
    ),
  );

  const walking = $derived(
    (app.execution === 'running' &&
      (runningKind === 'forward' ||
        runningKind === 'backward' ||
        runningKind === 'turn_left' ||
        runningKind === 'turn_right')) ||
      isManualMoving,
  );

  const sprinting = $derived(isManualSprinting);

  /** Posture active demandée au modèle 3D selon l'étape ou l'état du robot. */
  const effectivePosture = $derived(
    runningKind === 'sit' || runningKind === 'heart'
      ? 'sit'
      : runningKind === 'lie_down'
        ? 'lie_down'
        : runningKind === 'stand' ||
            runningKind === 'balance' ||
            runningKind === 'forward' ||
            runningKind === 'backward' ||
            runningKind === 'turn_left' ||
            runningKind === 'turn_right' ||
            runningKind === 'salute' ||
            runningKind === 'stretch' ||
            runningKind === 'jump'
          ? 'stand'
          : (app.status.posture ?? 'stand'),
  );

  /** Action expressive active (gestes 3D : saluer, cœur, étirement, saut). */
  const effectiveAction = $derived(
    runningKind === 'salute' ||
      runningKind === 'heart' ||
      runningKind === 'stretch' ||
      runningKind === 'jump'
      ? runningKind
      : null,
  );

  $effect(() => {
    const next = program;
    // `syncSteps` lit et réécrit la liste des étapes : sans `untrack`, l'effet
    // se prendrait pour sa propre dépendance et tournerait sans fin.
    untrack(() => {
      app.setProgram(next);
      app.syncSteps(next.statements);
    });
  });

  $effect(() => {
    if (!manualMode) return;
    const unsafe = Boolean(app.status.safetyReason);
    const disconnected = app.status.mode === 'real' && !app.status.connected;
    const executionStarted = app.execution === 'starting' || app.execution === 'running';
    const standbyActive = app.status.standby || app.status.standbyTransition !== null;
    if (unsafe || disconnected || executionStarted || standbyActive) {
      closeManual();
    }
  });

  onMount(() => {
    blocks = loadBlocks();
    app.connect();
    void app.refreshSettings();
    const poll = setInterval(() => void app.refreshStatus(), 2000);

    const checkRemote = () => {
      isRemoteMode =
        window.location.search.includes('remote') || window.location.hash.includes('remote');
    };
    window.addEventListener('popstate', checkRemote);
    window.addEventListener('hashchange', checkRemote);

    return () => {
      clearInterval(poll);
      window.removeEventListener('popstate', checkRemote);
      window.removeEventListener('hashchange', checkRemote);
      app.disconnect();
    };
  });

  function addBlock(kind: PlayBlockKind, index?: number): void {
    // Pendant une exécution, le programme envoyé ne bouge plus : modifier la
    // timeline donnerait l'illusion d'agir sur ce qui tourne.
    if (app.isBusy) {
      app.notice = {
        tone: 'warn',
        message: 'Attends la fin du programme avant de le modifier.',
      };
      return;
    }
    const next = [...blocks];
    const at =
      index === undefined ? next.length : Math.max(0, Math.min(index, next.length));
    next.splice(at, 0, createBlock(kind));
    blocks = next;
  }

  function removeBlock(id: string): void {
    blocks = blocks.filter((block) => block.id !== id);
  }

  function changeSeconds(id: string, seconds: number): void {
    blocks = blocks.map((block) =>
      block.id === id ? { ...block, seconds } : block,
    );
  }

  function changeDegrees(id: string, degrees: number): void {
    blocks = blocks.map((block) =>
      block.id === id ? { ...block, degrees } : block,
    );
  }

  function moveBlock(id: string, toIndex: number): void {
    const from = blocks.findIndex((block) => block.id === id);
    if (from < 0) return;
    const next = [...blocks];
    const [moved] = next.splice(from, 1);
    if (!moved) return;
    // Retirer l'élément décale tout ce qui le suit : l'index d'arrivée doit
    // être ajusté, sinon un glissement vers la droite atterrit un cran trop loin.
    const target = toIndex > from ? toIndex - 1 : toIndex;
    next.splice(Math.max(0, Math.min(target, next.length)), 0, moved);
    blocks = next;
  }

  function clearProgram(): void {
    if (app.isBusy) return;
    blocks = [];
    clearSavedBlocks();
    app.notice = null;
    app.closeBlockedNotice();
  }

  /**
   * Le switch ne coupe que la vérification de place du service.
   * Le couper est une décision d'adulte : on demande confirmation.
   */
  function toggleSafety(enabled: boolean): void {
    if (app.status.autonomousActive) return;
    if (enabled) {
      void app.setObstacleSafety(true);
      return;
    }
    showSafetyOffConfirm = true;
  }

  function confirmSafetyOff(): void {
    showSafetyOffConfirm = false;
    void app.setObstacleSafety(false);
  }

  /**
   * Une seule source pour le programme envoyé : on recompile juste avant de
   * partir, jamais depuis un état affiché qui aurait pu vieillir.
   */
  function start(): void {
    if (blocks.length === 0) {
      app.notice = {
        tone: 'warn',
        message: 'Glisse un bloc dans Mon Programme pour commencer.',
      };
      return;
    }
    const fresh = toProgram(blocks);
    if (!app.check(fresh)) return;
    app.requestStart(fresh);
  }

  function stop(): void {
    if (manualMode) {
      closeManual();
    }
    if (app.status.autonomousActive) {
      void app.toggleAutonomous();
    }
    void app.requestStop();
  }

  async function openManual(): Promise<void> {
    if (app.isBusy || app.status.safetyReason) return;
    if (await app.startManual()) {
      manualMode = true;
    }
  }

  function closeManual(): void {
    manualMode = false;
    void app.stopManual();
  }

  function openRobot(): void {
    if (manualMode) closeManual();
    showRobot = true;
  }

  function save(): void {
    if (blocks.length === 0) {
      app.notice = {
        tone: 'warn',
        message: 'Ajoute au moins un bloc avant de sauvegarder.',
      };
      return;
    }
    try {
      saveBlocks(blocks);
      downloadProgramJson(blocks);
      app.notice = {
        tone: 'ok',
        message: 'Programme sauvegardé et téléchargé en JSON (Téléchargements).',
      };
    } catch (error) {
      app.notice = {
        tone: 'error',
        message:
          error instanceof PlayStorageError
            ? error.message
            : 'Impossible de sauvegarder le programme.',
      };
    }
  }

  function triggerImport(): void {
    if (app.isBusy) {
      app.notice = {
        tone: 'warn',
        message: 'Attends la fin du programme avant d’importer.',
      };
      return;
    }
    fileInputEl?.click();
  }

  async function importFileDirect(file: File): Promise<void> {
    if (app.isBusy) {
      app.notice = {
        tone: 'warn',
        message: 'Attends la fin du programme avant d’importer.',
      };
      return;
    }
    try {
      const text = await file.text();
      const imported = parseBlocksFromJson(text);
      if (imported.length === 0) {
        app.notice = {
          tone: 'warn',
          message: 'Le fichier JSON ne contient aucun bloc valide.',
        };
        return;
      }
      blocks = imported;
      saveBlocks(blocks);
      app.notice = {
        tone: 'ok',
        message: `Programme importé avec succès (${imported.length} bloc${imported.length > 1 ? 's' : ''}).`,
      };
    } catch (error) {
      app.notice = {
        tone: 'error',
        message:
          error instanceof PlayStorageError
            ? error.message
            : 'Fichier JSON invalide ou illisible.',
      };
    }
  }

  async function handleFileInputChange(event: Event): Promise<void> {
    const target = event.target as HTMLInputElement;
    const file = target.files?.[0];
    if (file) {
      await importFileDirect(file);
    }
    target.value = '';
  }
</script>

<input
  type="file"
  bind:this={fileInputEl}
  accept=".json,application/json"
  style="display: none;"
  onchange={handleFileInputChange}
/>

{#if isRemoteMode}
  <MobileGamepad />
{:else}
<div class="app">
  <PlayHeader
    status={app.status}
    busy={app.isBusy || manualMode}
    onManual={() => void openManual()}
    onToggleAutonomous={() => void app.toggleAutonomous()}
    onSave={save}
    onOpenRobot={openRobot}
    onToggleSafety={toggleSafety}
    onToggleStandby={(enabled) => void app.setStandby(enabled)}
  />

  {#if app.status.safetyReason}
    <div class="safety" role="alert" aria-live="assertive">
      <span class="safety__icon" aria-hidden="true">🛑</span>
      <div class="safety__text">
        <strong>Le robot s’est arrêté pour ta sécurité.</strong>
        <p>{app.status.safetyReason}</p>
      </div>
    </div>
  {:else if app.status.recoveryReason}
    <div class="safety safety--info" role="status" aria-live="polite">
      <span class="safety__icon" aria-hidden="true">🐕</span>
      <div class="safety__text">
        <p>{app.status.recoveryReason}</p>
      </div>
    </div>
  {/if}

  <main class="app__main" class:app__main--manual={manualMode}>
    <div class="app__library">
      <BlockLibrary
        onAdd={(kind) => addBlock(kind)}
        onRemove={removeBlock}
        onSettings={() => (showSettings = true)}
        onHelp={() => (showHelp = true)}
      />
    </div>

    <div class="app__program">
      <ProgramTimeline
        {blocks}
        {runningIndex}
        busy={app.isBusy || manualMode}
        blocked={Boolean(app.status.safetyReason)}
        autonomousActive={Boolean(app.status.autonomousActive)}
        notice={app.notice}
        onAdd={addBlock}
        onRemove={removeBlock}
        onChangeSeconds={changeSeconds}
        onChangeDegrees={changeDegrees}
        onMove={moveBlock}
        onStart={start}
        onStop={stop}
        onClear={clearProgram}
        onChooseFile={triggerImport}
        onImportFile={(file) => void importFileDirect(file)}
      />
    </div>

    <div class="app__robot">
      <RobotStage
        status={app.status}
        {walking}
        {sprinting}
        posture={effectivePosture}
        action={effectiveAction}
        resetRun={app.execution === 'starting'}
        onOpenRobot={openRobot}
        onResetSimulation={() => void app.resetSimulation()}
      />
    </div>

    {#if manualMode}
      <div class="app__manual">
        <ManualPanel
          robotReady={app.status.mode === 'simulation' || (app.status.mode === 'real' && app.status.connected)}
          onMove={(direction, seq, sprint) => app.moveManual(direction, seq, 'keyboard', sprint)}
          onRelease={(seq) => void app.moveManual(null, seq)}
          onJump={() => app.jumpManual()}
          onClose={closeManual}
        />
      </div>
    {/if}
  </main>
</div>

{#if showHelp}
  <HelpModal onClose={() => (showHelp = false)} />
{/if}

{#if showMode}
  <ModeSwitch onClose={() => (showMode = false)} />
{/if}

{#if showSettings}
  <SettingsPanel onClose={() => (showSettings = false)} />
{/if}

{#if showRobot}
  <div class="modal-backdrop" role="presentation">
    <div class="modal modal--etroit" role="dialog" aria-modal="true" aria-label="Robot réel">
      <RobotConnect onClose={() => (showRobot = false)} />
    </div>
  </div>
{/if}

{#if app.pendingStart}
  <div class="modal-backdrop" role="presentation">
    <div class="modal" role="dialog" aria-modal="true" aria-labelledby="confirm-start">
      <div class="modal__header">
        <span class="modal__emoji" aria-hidden="true">🤖</span>
        <div>
          <h2 class="modal__title" id="confirm-start">Le robot va vraiment bouger</h2>
          <p class="modal__subtitle">Dernière confirmation</p>
        </div>
      </div>
      <div class="modal__body">
        <p>
          Tu es en <strong>mode robot réel</strong>. Vérifie que la zone est
          dégagée et qu’un adulte peut arrêter le robot à tout moment.
        </p>
        <p>Es-tu prêt&nbsp;?</p>
      </div>
      <div class="modal__footer">
        <button type="button" class="btn btn--ghost" onclick={() => app.cancelPendingStart()}>
          Pas encore
        </button>
        <button type="button" class="btn btn--danger" onclick={() => app.confirmPendingStart()}>
          Oui, démarrer
        </button>
      </div>
    </div>
  </div>
{/if}

{#if app.blockedNotice}
  <BlockedPopup
    title={app.blockedNotice.title}
    message={app.blockedNotice.message}
    kind={app.blockedNotice.kind}
    onClose={() => app.closeBlockedNotice()}
  />
{/if}

{#if showSafetyOffConfirm}
  <div class="modal-backdrop" role="presentation">
    <div
      class="modal"
      role="alertdialog"
      aria-modal="true"
      aria-labelledby="confirm-safety-off"
    >
      <div class="modal__header">
        <span class="modal__emoji" aria-hidden="true">⚠️</span>
        <div>
          <h2 class="modal__title" id="confirm-safety-off">Désactiver la sécurité ?</h2>
          <p class="modal__subtitle">Décision d’adulte</p>
        </div>
      </div>
      <div class="modal__body">
        <p>
          Le service ne vérifiera plus la distance avant un pas. Le robot
          pourrait donc avancer vers un obstacle.
        </p>
        <p>
          L’anti-obstacle interne du Go2 reste actif, mais il ne suffit pas à
          garantir une zone dégagée. Garde la main sur l’arrêt.
        </p>
      </div>
      <div class="modal__footer">
        <button
          type="button"
          class="btn btn--ghost"
          onclick={() => (showSafetyOffConfirm = false)}
        >
          Annuler
        </button>
        <button type="button" class="btn btn--danger" onclick={confirmSafetyOff}>
          Désactiver
        </button>
      </div>
    </div>
  </div>
{/if}

{/if}

{#if app.status.standby || app.status.standbyTransition !== null}
  <StandbyOverlay
    status={app.status}
    onWake={() => void app.setStandby(false)}
  />
{/if}

<style>
  .app {
    display: flex;
    flex-direction: column;
    height: 100vh;
    min-height: 0;
    padding: 14px 18px 18px;
    box-sizing: border-box;
    overflow: hidden;
  }

  .safety {
    display: flex;
    align-items: flex-start;
    gap: 12px;
    margin: 0 0 14px;
    padding: 12px 16px;
    border: 1px solid #a33a45;
    border-radius: 16px;
    background: linear-gradient(180deg, #3b1b20, #2d1519);
    color: #ffd7db;
    box-shadow: 0 10px 24px rgb(0 0 0 / 28%);
  }

  .safety--info {
    border-color: #2f6d55;
    background: linear-gradient(180deg, #1c3a30, #16302a);
    color: #d6f2e4;
  }

  .safety--info .safety__text p {
    color: #a9d8c3;
  }

  .safety__icon {
    font-size: 24px;
    line-height: 1.1;
  }

  .safety__text {
    min-width: 0;
  }

  .safety__text strong {
    display: block;
    font-size: 17px;
    letter-spacing: -0.01em;
  }

  .safety__text p {
    margin: 3px 0 0;
    color: #f3b6bd;
    font-size: 14px;
    line-height: 1.35;
  }

  .app__main {
    flex: 1;
    min-height: 0;
    display: grid;
    grid-template-columns: minmax(0, 1fr) clamp(320px, 29%, 460px);
    grid-template-rows: minmax(0, 1fr) auto;
    grid-template-areas:
      'library robot'
      'program robot';
    gap: 16px;
  }

  @media (min-width: 1700px) {
    .app__main {
      grid-template-columns: minmax(0, 1fr) clamp(380px, 28%, 560px);
      gap: 20px;
    }
  }

  .app__library {
    grid-area: library;
    display: flex;
    min-width: 0;
    min-height: 0;
  }

  .app__library :global(section) {
    flex: 1;
  }

  .app__program {
    grid-area: program;
    min-width: 0;
  }

  .app__robot {
    grid-area: robot;
    display: flex;
    min-width: 0;
    min-height: 0;
  }

  .app__robot :global(aside) {
    flex: 1;
  }

  /* Le flou est appliqué aux blocs eux-mêmes : il reste net même dans les
     navigateurs qui ignorent `backdrop-filter`. */
  .app__main--manual .app__library,
  .app__main--manual .app__program {
    filter: blur(9px);
    pointer-events: none;
    user-select: none;
  }

  /* Le mode manuel recouvre la bibliothèque et le programme, pas le robot :
     l'adulte garde la vue du chien pendant qu'il le pilote. */
  .app__manual {
    grid-area: 1 / 1 / 3 / 2;
    z-index: 8;
    display: flex;
    align-items: center;
    justify-content: center;
    min-width: 0;
    min-height: 0;
    padding: 8px;
    overflow: hidden;
    border-radius: 24px;
    background: rgb(20 23 30 / 58%);
    backdrop-filter: blur(9px);
    -webkit-backdrop-filter: blur(9px);
  }

  @media (max-height: 520px) {
    .app__manual {
      overflow-y: auto;
    }
  }

  /* Fenêtre de branchement : étroite, elle ne prend pas l'écran des blocs. */
  .modal--etroit {
    max-width: 380px;
  }

  .modal__emoji {
    font-size: 26px;
    line-height: 1;
  }

  @media (max-width: 1080px) {
    .app {
      height: auto;
      min-height: 100vh;
    }

    .app__main {
      grid-template-columns: minmax(0, 1fr);
      grid-template-rows: auto auto auto;
      grid-template-areas:
        'library'
        'program'
        'robot';
    }

    .app__library {
      min-height: 420px;
    }

    /* Empilée, la vue du robot deviendrait une bande très large : le dessin
       est en portrait, un cadre carré garde le chien entier. */
    .app__robot {
      width: 100%;
      max-width: 620px;
      min-height: 0;
      margin: 0 auto;
    }

    .app__robot :global(.scene) {
      flex: none;
      min-height: 0;
      aspect-ratio: 1 / 1;
    }

    .app__manual {
      align-items: flex-start;
    }
  }

  @media (max-width: 640px) {
    .app {
      padding: 10px;
    }

    .app__main {
      gap: 12px;
    }

    .app__library {
      min-height: 380px;
    }

    .app__manual {
      padding: 12px;
    }
  }
</style>
