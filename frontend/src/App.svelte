<script lang="ts">
  /**
   * GO2 Scratch — écran principal.
   *
   * Organisation en quatre zones :
   *  1. barre supérieure   (TopBar)
   *  2. palette de blocs   (rendue par Blockly dans l'éditeur)
   *  3. espace de saisie   (BlocklyEditor) — occupe TOUTE la place restante
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
  import SettingsPanel from './components/SettingsPanel.svelte';
  import { app } from './lib/stores/app.svelte';
  import type { RobotCommand } from './lib/robot/commands';

  type EditorApi = {
    serialize: () => string;
    load: (xml: string) => void;
    clear: () => void;
    refresh: () => RobotCommand[];
  };

  let editor = $state<EditorApi | null>(null);
  let commands = $state<RobotCommand[]>([]);
  let compileIssues = $state<string[]>([]);
  let showHelp = $state(false);
  let showMode = $state(false);
  let showSettings = $state(false);

  onMount(() => {
    app.connect();
    void app.refreshSettings();
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
    // La liste des étapes suit immédiatement le programme : afficher
    // « Avancer de 120 cm » pendant qu'un 75 est prêt à partir, ce serait
    // mentir. Le verdict, lui, reste à l'initiative de « Vérifier ».
    app.syncSteps(next);
    if (issues.length > 0 && !app.isBusy) {
      app.notice = { tone: 'error', message: issues[0] ?? 'Programme incomplet.' };
    }
  }

  /**
 * Recompile avant toute action.
 *
 * Vérifier et Démarrer ne doivent jamais travailler sur un état périmé :
 * l'enfant a pu déposer ou modifier un bloc depuis le dernier rendu.
 * On interroge donc l'éditeur à l'instant même, sans dépendre des événements
 * de changement de Blockly.
 */
function currentProgram(): { commands: RobotCommand[]; issues: string[] } {
    if (!editor) {
      return { commands: [], issues: ['L’éditeur n’est pas prêt. Recharge la page.'] };
    }
    const fresh = editor.refresh();
    return { commands: fresh, issues: compileIssues };
  }

  function runCheck(): void {
    const program = currentProgram();
    commands = program.commands;
    if (program.issues.length > 0) {
      app.notice = { tone: 'error', message: program.issues[0] ?? 'Programme incomplet.' };
      return;
    }
    app.check(commands);
  }

  function runStart(): void {
    app.requestStart(currentProgram().commands);
  }
</script>

<div class="app">
  <TopBar onHelp={() => (showHelp = true)} onSettings={() => (showSettings = true)} />

  <main class="app__main">
    <div class="app__workspace">
      <BlocklyEditor onChange={onWorkspaceChange} registerApi={(api) => (editor = api)} />
    </div>

    <aside class="app__side">
      <ControlPanel onCheck={runCheck} onStart={runStart} />

      <div class="app__quick">
        <button type="button" class="quick" onclick={() => (showMode = true)}>
          <span class="quick__icon" aria-hidden="true">
            {app.status.mode === 'simulation' ? '🧪' : '🤖'}
          </span>
          <span class="quick__text">
            <span class="quick__label">
              {app.status.mode === 'simulation' ? 'Mode simulation' : 'Mode robot réel'}
            </span>
            <span class="quick__hint">
              {app.status.mode === 'simulation' ? 'Activer le robot' : 'Revenir en simulation'}
            </span>
          </span>
        </button>

        <button type="button" class="quick" onclick={() => (showSettings = true)}>
          <span class="quick__icon" aria-hidden="true">⚙️</span>
          <span class="quick__text">
            <span class="quick__label">Configuration</span>
            <span class="quick__hint">Réglages du robot</span>
          </span>
        </button>
      </div>

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

{#if showSettings}
  <SettingsPanel onClose={() => (showSettings = false)} />
{/if}

{#if app.pendingStart}
  <div class="modal-backdrop" role="presentation">
    <div class="modal" role="dialog" aria-modal="true" aria-labelledby="confirm-start">
      <div class="modal__header">
        <span style="font-size:26px" aria-hidden="true">🤖</span>
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
  }

  .app__main {
    flex: 1;
    min-height: 0;
    display: grid;
    /* L'espace de blocs prend toute la largeur restante ; la colonne de
       contrôle a une largeur fixe et ne peut pas le réduire. */
    grid-template-columns: minmax(0, 1fr) var(--side-w);
    gap: var(--gutter);
    padding: var(--gutter);
  }

  .app__workspace {
    /* grow + shrink + base nulle : l'éditeur occupe la cellule entière. */
    flex: 1 1 0;
    min-width: 0;
    min-height: 0;
    display: flex;
  }

  .app__side {
    display: flex;
    flex-direction: column;
    gap: 12px;
    min-width: 0;
    min-height: 0;
    overflow-y: auto;
    /* Marge pour ne pas coller la barre de défilement au bord de l'écran. */
    padding-right: 2px;
  }

  .app__quick {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 10px;
    flex: none;
  }

  .quick {
    display: flex;
    align-items: center;
    gap: 11px;
    padding: 12px 14px;
    border: 1px solid var(--line);
    border-radius: var(--radius-l);
    background: var(--surface);
    box-shadow: var(--shadow-s);
    font-family: inherit;
    text-align: left;
    cursor: pointer;
    transition:
      transform 0.14s ease,
      box-shadow 0.16s ease,
      border-color 0.16s ease;
  }

  .quick:hover {
    transform: translateY(-2px);
    box-shadow: var(--shadow-m);
    border-color: var(--line-strong);
  }

  .quick:focus-visible {
    outline: 3px solid var(--brand-400);
    outline-offset: 2px;
  }

  .quick__icon {
    font-size: 22px;
    line-height: 1;
    flex: none;
  }

  .quick__text {
    display: flex;
    flex-direction: column;
    min-width: 0;
  }

  .quick__label {
    font-size: 13.5px;
    font-weight: 750;
    color: var(--ink-900);
    letter-spacing: -0.01em;
  }

  .quick__hint {
    font-size: 11.5px;
    color: var(--ink-500);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  /* En dessous de 1180 px, la colonne latérale passe sous l'éditeur. */
  @media (max-width: 1179px) {
    .app__main {
      grid-template-columns: minmax(0, 1fr);
      grid-template-rows: minmax(340px, 1fr) auto;
      overflow-y: auto;
    }

    .app__side {
      overflow: visible;
    }
  }

  @media (max-width: 620px) {
    .app__quick {
      grid-template-columns: 1fr;
    }
  }
</style>