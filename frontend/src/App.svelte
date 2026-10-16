<script lang="ts">
  /**
   * GO2 Scratch — écran principal.
   *
   * Organisation en quatre zones :
   *  1. barre supérieure   (TopBar)
   *  2. palette de blocs   (rendue par Blockly dans l'éditeur)
   *  3. espace de saisie   (BlocklyEditor)
   *  4. zone de contrôle   (ControlPanel + MissionPanel)
   *
   * L'interface n'accède JAMAIS au robot : elle passe par lib/api/client.
   */
  import { onMount } from 'svelte';
  import TopBar from './components/TopBar.svelte';
  import BlocklyEditor from './components/BlocklyEditor.svelte';
  import ControlPanel from './components/ControlPanel.svelte';
  import MissionPanel from './components/MissionPanel.svelte';
  import HelpModal from './components/HelpModal.svelte';
  import ModeSwitch from './components/ModeSwitch.svelte';
  import { app } from './lib/stores/app.svelte';
  import type { RobotCommand } from './lib/robot/commands';

  type EditorApi = {
    serialize: () => string;
    load: (xml: string) => void;
    clear: () => void;
  };

  let projectName = $state('Ma première mission');
  let editor = $state<EditorApi | null>(null);
  let commands = $state<RobotCommand[]>([]);
  let compileIssues = $state<string[]>([]);
  let showHelp = $state(false);
  let showMode = $state(false);

  onMount(() => {
    app.connect();
    const poll = setInterval(() => void app.refreshStatus(), 2000);
    return () => {
      clearInterval(poll);
      app.disconnect();
    };
  });

  /** Le compilateur a produit un nouveau programme : on le conserve. */
  function onWorkspaceChange(next: readonly RobotCommand[], issues: readonly string[]): void {
    commands = [...next];
    compileIssues = [...issues];
    app.setCommands(next);
    if (issues.length > 0 && app.execution !== 'running') {
      app.notice = { tone: 'error', message: issues[0] ?? 'Programme incomplet.' };
    }
  }

  function runCheck(): void {
    if (compileIssues.length > 0) {
      app.notice = { tone: 'error', message: compileIssues[0] ?? 'Programme incomplet.' };
      return;
    }
    app.check(commands);
  }

  function runStart(): void {
    app.requestStart(commands);
  }
</script>

<div class="app">
  <TopBar {projectName} onHelp={() => (showHelp = true)} />

  <main class="app__main">
    <section class="app__workspace" aria-label="Espace de programmation">
      <BlocklyEditor onChange={onWorkspaceChange} registerApi={(api) => (editor = api)} />
    </section>

    <aside class="app__side">
      <ControlPanel onCheck={runCheck} onStart={runStart} />

      <button type="button" class="btn btn--ghost mode-button" onclick={() => (showMode = true)}>
        <span aria-hidden="true">{app.status.mode === 'simulation' ? '🧪' : '🤖'}</span>
        {app.status.mode === 'simulation'
          ? 'Passer en mode robot réel'
          : 'Revenir en mode simulation'}
      </button>

      <MissionPanel {editor} />
    </aside>
  </main>
</div>

{#if showHelp}
  <HelpModal onClose={() => (showHelp = false)} />
{/if}

{#if showMode}
  <ModeSwitch onClose={() => (showMode = false)} />
{/if}

{#if app.pendingStart}
  <div class="modal-backdrop" role="presentation">
    <div class="modal" role="dialog" aria-modal="true" aria-labelledby="confirm-start">
      <div class="modal__header">
        <span style="font-size:26px" aria-hidden="true">🤖</span>
        <h2 class="modal__title" id="confirm-start">Le robot va vraiment bouger</h2>
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
  }

  .app__main {
    flex: 1;
    display: grid;
    grid-template-columns: minmax(0, 1fr) 360px;
    gap: 14px;
    padding: 14px;
    min-height: 0;
  }

  .app__workspace {
    min-width: 0;
    min-height: 0;
    display: flex;
  }

  .app__side {
    display: flex;
    flex-direction: column;
    gap: 12px;
    min-height: 0;
    overflow-y: auto;
  }

  .mode-button {
    flex: none;
  }

  /* Écrans étroits : la colonne latérale passe dessous du workspace.
     Seuil à 1100 px pour que la disposition en deux colonnes — celle prévue
     pour 1366 x 768 — reste celle par défaut. */
  @media (max-width: 1099px) {
    .app__main {
      grid-template-columns: minmax(0, 1fr);
      grid-template-rows: minmax(280px, 1fr) auto;
      overflow-y: auto;
    }

    .app__side {
      overflow: visible;
    }
  }
</style>