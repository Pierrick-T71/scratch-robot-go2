<script lang="ts">
  /**
   * Enveloppe l'editeur Blockly : injection, chargement de mission,
   * compilation a la demande. Isole le reste de l'interface de l'API Blockly.
   */
  import { onMount } from 'svelte';
  import {
    Blockly,
    applyFrenchLocale,
    buildInjectOptions,
    defaultProgramXml,
  } from '../lib/blockly/workspace';
  import { compileWorkspace } from '../lib/blockly/compiler';
  import { registerGo2Blocks } from '../lib/blockly/blocks';
  import type { RobotCommand } from '../lib/robot/commands';

  interface Props {
    /** Commandes compilees, remises a chaque modification du programme. */
    onChange: (commands: readonly RobotCommand[], issues: readonly string[]) => void;
    /** Recupere le XML serialise (sauvegarde de mission). */
    registerApi: (api: { serialize: () => string; load: (xml: string) => void; clear: () => void }) => void;
  }

  let { onChange, registerApi }: Props = $props();

  let container: HTMLDivElement | undefined = $state();
  let workspace: Blockly.WorkspaceSvg | null = null;

  function serialize(): string {
    if (!workspace) return defaultProgramXml();
    return Blockly.Xml.domToText(Blockly.Xml.workspaceToDom(workspace, false));
  }

  function load(xml: string): void {
    if (!workspace) return;
    workspace.clear();
    try {
      Blockly.Xml.domToWorkspace(Blockly.utils.xml.textToDom(xml), workspace);
    } catch {
      // Fichier de programme refuse : on repart du programme vide plutot que
      // de laisser un etat partiel dans l'editeur.
      Blockly.Xml.domToWorkspace(
        Blockly.utils.xml.textToDom(defaultProgramXml()),
        workspace,
      );
    }
    publish();
  }

  function clear(): void {
    if (!workspace) return;
    workspace.clear();
    Blockly.Xml.domToWorkspace(Blockly.utils.xml.textToDom(defaultProgramXml()), workspace);
    publish();
  }

  function publish(): void {
    if (!workspace) return;
    const result = compileWorkspace(Blockly);
    onChange(result.commands, result.issues.map((i) => i.message));
  }

  onMount(() => {
    if (!container) return;

    applyFrenchLocale();
    registerGo2Blocks();
    workspace = Blockly.inject(container, buildInjectOptions());
    Blockly.Xml.domToWorkspace(Blockly.utils.xml.textToDom(defaultProgramXml()), workspace);

    registerApi({ serialize, load, clear });

    // Point d'accroche pour les tests d'interface (Playwright) et le débogage.
    // Exposé UNIQUEMENT en développement : jamais dans la version livrée.
    if (import.meta.env.DEV) {
      (globalThis as Record<string, unknown>)['__go2Blockly'] = {
        workspace,
        load,
        serialize,
        clear,
      };
    }

    const listener = (event: Blockly.Events.Abstract) => {
      // Inutile de recompiler a chaque simple deplacement de bloc.
      if (event.isUiEvent) return;
      publish();
    };
    workspace.addChangeListener(listener);

    publish();

    return () => {
      workspace?.removeChangeListener(listener);
      workspace?.dispose();
      workspace = null;
      if (import.meta.env.DEV) {
        delete (globalThis as Record<string, unknown>)['__go2Blockly'];
      }
    };
  });
</script>

<div class="editor">
  <div class="editor__hint">
    <strong>Astuce&nbsp;:</strong> prends un bloc dans la palette à gauche et
    accroche-le sous le bloc de départ.
  </div>
  <div class="editor__canvas" bind:this={container}></div>
</div>

<style>
  .editor {
    display: flex;
    flex-direction: column;
    height: 100%;
    min-height: 0;
    background: var(--paper);
    border: 1px solid var(--ink-300);
    border-radius: var(--radius-l);
    overflow: hidden;
    box-shadow: var(--shadow-s);
  }

  .editor__hint {
    padding: 8px 14px;
    background: var(--brand-100);
    color: var(--brand-600);
    font-size: 13px;
    border-bottom: 1px solid #c9d8ff;
  }

  .editor__canvas {
    flex: 1;
    min-height: 0;
  }
</style>