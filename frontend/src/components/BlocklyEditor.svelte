<script lang="ts">
  /**
   * Enveloppe l'éditeur Blockly : injection, chargement de mission,
   * compilation a la demande. Isole le reste de l'interface de l'API Blockly.
   *
   * Règle de mise en page : cet éditeur occupe TOUTE la surface restante.
   * On force `Blockly.inject` à mesurer son conteneur, sinon Blockly garde
   * une taille figée au premier rendu et l'espace vide n'est pas utilisé.
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
    registerApi: (api: {
      serialize: () => string;
      load: (xml: string) => void;
      clear: () => void;
    }) => void;
  }

  let { onChange, registerApi }: Props = $props();

  let container: HTMLDivElement | undefined = $state();
  let workspace: Blockly.WorkspaceSvg | null = null;
  let ro: ResizeObserver | null = null;

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

  /**
   * Cale exactement la zone de travail sur son conteneur.
   *
   * `workspace.resize()` suffit dans le cas général, mais on repasse aussi par
   * `svgResize()` : c'est l'appel de bas niveau qui recalcule le SVG, ses
   * barres de défilement et la grille. Les deux sont idempotents.
   */
  function applySize(): void {
    if (!workspace || !container) return;
    const { width, height } = container.getBoundingClientRect();
    if (width < 1 || height < 1) return;
    workspace.resize();
    Blockly.svgResize(workspace);
  }

  // Zoom : on passe par les méthodes de WorkspaceSvg (`zoomCenter`, `setScale`)
  // plutôt que par un helper global, plus simple à typer et à borner.
  const ZOOM_STEP = 1.2;
  const MIN_SCALE = 0.4;
  const MAX_SCALE = 1.6;

  function zoomIn(): void {
    if (!workspace) return;
    workspace.setScale(clampScale(workspace.getScale() * ZOOM_STEP));
  }

  function zoomOut(): void {
    if (!workspace) return;
    workspace.setScale(clampScale(workspace.getScale() / ZOOM_STEP));
  }

  function zoomReset(): void {
    workspace?.setScale(1);
  }

  function clampScale(scale: number): number {
    return Math.min(MAX_SCALE, Math.max(MIN_SCALE, scale));
  }

  onMount(() => {
    if (!container) return;

    applyFrenchLocale();
    registerGo2Blocks();

    // `resize` n'est pas une option de `inject` : Blockly s'abonne lui-même aux
    // redimensionnements de fenêtre. On pilote le nôtre via le ResizeObserver
    // ci-dessous, ce qui couvre aussi le redimensionnement de la colonne.
    workspace = Blockly.inject(container, buildInjectOptions());

    Blockly.Xml.domToWorkspace(Blockly.utils.xml.textToDom(defaultProgramXml()), workspace);

    registerApi({ serialize, load, clear });

    // Point d'accroche pour les tests d'interface et le débogage.
    // Exposé UNIQUEMENT en développement : jamais dans la version livrée.
    if (import.meta.env.DEV) {
      (globalThis as Record<string, unknown>)['__go2Blockly'] = {
        workspace,
        load,
        serialize,
        clear,
      };
    }

    ro = new ResizeObserver(() => {
      applySize();
    });
    ro.observe(container);

    // Deux `requestAnimationFrame` : au premier, la mise en page CSS est
    // faite mais le conteneur peut encore être en cours de calcul ; au second,
    // les dimensions définitives sont connues. Sans cela, l'éditeur peut rester
    // à sa taille d'injection sur les premières frames.
    requestAnimationFrame(() => {
      requestAnimationFrame(applySize);
    });

    const listener = (event: Blockly.Events.Abstract) => {
      // Inutile de recompiler a chaque simple deplacement de bloc.
      if (event.isUiEvent) return;
      publish();
    };
    workspace.addChangeListener(listener);

    publish();

    return () => {
      ro?.disconnect();
      ro = null;
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
  <div class="editor__bar">
    <p class="editor__hint">
      <span aria-hidden="true">💡</span>
      Glisse un bloc de la palette et <strong>accroche-le</strong> sous le bloc
      de départ.
    </p>
    <div class="editor__tools">
      <button
        type="button"
        class="btn btn--ghost btn--sm btn--icon"
        onclick={zoomOut}
        title="Dézoomer"
        aria-label="Dézoomer"
      >
        <span aria-hidden="true">🔍−</span>
      </button>
      <button
        type="button"
        class="btn btn--ghost btn--sm btn--icon"
        onclick={zoomReset}
        title="Réinitialiser le zoom"
        aria-label="Réinitialiser le zoom"
      >
        <span aria-hidden="true">🎯</span>
      </button>
      <button
        type="button"
        class="btn btn--ghost btn--sm btn--icon"
        onclick={zoomIn}
        title="Zoomer"
        aria-label="Zoomer"
      >
        <span aria-hidden="true">🔍+</span>
      </button>
    </div>
  </div>

  <div class="editor__canvas" bind:this={container}></div>
</div>

<style>
  .editor {
    display: flex;
    flex-direction: column;
    /* Occupe toute la place disponible : c'est la zone principale. */
    flex: 1 1 auto;
    width: 100%;
    min-width: 0;
    min-height: 0;
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: var(--radius-xl);
    box-shadow: var(--shadow-m);
    overflow: hidden;
  }

  .editor__bar {
    display: flex;
    align-items: center;
    gap: 14px;
    padding: 9px 14px;
    background: var(--surface-2);
    border-bottom: 1px solid var(--line);
    flex: none;
  }

  .editor__hint {
    margin: 0;
    font-size: 13px;
    color: var(--ink-500);
    display: flex;
    align-items: center;
    gap: 7px;
  }

  .editor__hint strong {
    color: var(--ink-700);
  }

  .editor__tools {
    margin-left: auto;
    display: flex;
    gap: 6px;
    flex: none;
  }

  .editor__canvas {
    /* Point clé : 0 en flex-basis, sinon la barre mange la hauteur. */
    flex: 1 1 0;
    min-height: 0;
    min-width: 0;
    position: relative;
    background: var(--canvas);
  }

  /* Grille de fond très légère, pour que la zone ne soit pas un aplat vide. */
  .editor__canvas::before {
    content: '';
    position: absolute;
    inset: 0;
    pointer-events: none;
    background-image: radial-gradient(circle, rgb(15 23 41 / 5%) 1px, transparent 1px);
    background-size: 26px 26px;
  }
</style>