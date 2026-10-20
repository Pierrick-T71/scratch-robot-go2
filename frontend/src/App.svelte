<script lang="ts">
  /**
   * Go2 Play — écran principal.
   *
   * Trois zones :
   *  1. la barre du haut     (PlayHeader) : identité, Lancer / Arrêter / Sauvegarder ;
   *  2. la bibliothèque      (BlockLibrary) et « Mon Programme » (ProgramTimeline) ;
   *  3. la vue du robot      (RobotStage), à droite, sur toute la hauteur.
   *
   * L'interface n'accède jamais au robot : tout passe par `app` (lib/stores),
   * qui parle au service. Les six blocs sont traduits en `Program` par
   * `lib/play/blocks` — la même structure que le service connaît déjà.
   */
  import { onMount, untrack } from 'svelte';
  import PlayHeader from './components/play/PlayHeader.svelte';
  import BlockLibrary from './components/play/BlockLibrary.svelte';
  import ProgramTimeline from './components/play/ProgramTimeline.svelte';
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
    loadBlocks,
    PlayStorageError,
    saveBlocks,
  } from './lib/play/storage';

  let blocks = $state<PlayBlock[]>([]);

  let showHelp = $state(false);
  let showMode = $state(false);
  let showSettings = $state(false);
  let showRobot = $state(false);

  /** Ce que voit l'enfant EST ce qui part : une seule source de vérité. */
  const program = $derived(toProgram(blocks));

  /** Index du bloc en cours d'exécution (null hors exécution). */
  const runningIndex = $derived(
    app.steps.find((step) => step.state === 'running')?.index ?? null,
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

  onMount(() => {
    blocks = loadBlocks();
    app.connect();
    void app.refreshSettings();
    const poll = setInterval(() => void app.refreshStatus(), 2000);
    return () => {
      clearInterval(poll);
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
    void app.requestStop();
  }

  function save(): void {
    try {
      saveBlocks(blocks);
      app.notice = {
        tone: 'ok',
        message: 'Programme sauvegardé sur cet appareil.',
      };
    } catch (error) {
      app.notice = {
        tone: 'error',
        message:
          error instanceof PlayStorageError
            ? error.message
            : 'Impossible de sauvegarder sur cet appareil.',
      };
    }
  }
</script>

<div class="app">
  <PlayHeader
    status={app.status}
    busy={app.isBusy}
    blockCount={blocks.length}
    onStart={start}
    onStop={stop}
    onSave={save}
    onOpenRobot={() => (showRobot = true)}
  />

  <main class="app__main">
    <div class="app__library">
      <BlockLibrary
        onAdd={(kind) => addBlock(kind)}
        onSettings={() => (showSettings = true)}
        onHelp={() => (showHelp = true)}
      />
    </div>

    <div class="app__program">
      <ProgramTimeline
        {blocks}
        {runningIndex}
        busy={app.isBusy}
        notice={app.notice}
        onAdd={addBlock}
        onRemove={removeBlock}
        onChangeSeconds={changeSeconds}
        onChangeDegrees={changeDegrees}
        onMove={moveBlock}
        onStart={start}
        onClear={clearProgram}
      />
    </div>

    <div class="app__robot">
      <RobotStage
        status={app.status}
        onRefresh={() => void app.refreshStatus()}
        onOpenRobot={() => (showRobot = true)}
      />
    </div>
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

<style>
  .app {
    display: flex;
    flex-direction: column;
    height: 100vh;
    min-height: 0;
    padding: 14px 18px 18px;
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
  }
</style>
