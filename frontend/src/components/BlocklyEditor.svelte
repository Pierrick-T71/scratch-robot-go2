<script lang="ts">
  /**
   * Enveloppe l'éditeur Blockly : injection, chargement de mission,
   * compilation à la demande. Isole le reste de l'interface de l'API Blockly.
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
  import { compileWorkspace, type CompileResult } from '../lib/blockly/compiler';
  import { registerGo2Blocks } from '../lib/blockly/blocks';
  import type { Program } from '../lib/robot/program';

  interface Props {
    /** Programme compilé, remis à chaque modification. */
    onChange: (result: CompileResult) => void;
    /**
     * API de l'éditeur.
     *
     * `refresh()` RECOMPILE et renvoie l'état courant. Vérifier et Démarrer
     * l'appellent systématiquement : on ne doit jamais valider un programme à
     * partir d'un état potentiellement périmé, et cela ne dépend d'aucun
     * événement de changement Blockly.
     */
    registerApi: (api: {
      serialize: () => string;
      load: (xml: string) => void;
      clear: () => void;
      refresh: () => Program;
    }) => void;
  }

  let { onChange, registerApi }: Props = $props();

  let container: HTMLDivElement | undefined = $state();
let workspace: Blockly.WorkspaceSvg | null = null;
let ro: ResizeObserver | null = null;

  /**
   * `true` pendant le chargement d'un programme.
   *
   * ⚠️ `domToWorkspace` crée les blocs un par un et déclenche un événement de
   * changement à chaque étape.编译ée à cet instant, la compilation voyait le
   * bloc enfant encore détaché et annonçait « un bloc est seul » — sur un
   * programme parfaitement valide. L'enfant l'aurait lu et cherché une
   * erreur qui n'existait pas.
   */
  let loading = false;

  function serialize(): string {
    if (!workspace) return defaultProgramXml();
    return Blockly.Xml.domToText(Blockly.Xml.workspaceToDom(workspace, false));
  }

  /**
   * Recharge une mission.
   *
   * ⚠️ Les menus déroulants sont réinitialisés : un fichier enregistré avant
   * une modification des choix (par exemple 0,25 s, qui n'existe plus) est
   * ramené à une valeur proposée. `FieldDropdown.setValue` accepte sinon
   * n'importe quelle chaîne, et le robot partirait avec une durée que personne
   * n'a choisie.
   */
  function load(xml: string): void {
    if (!workspace) return;
    loading = true;
    try {
      workspace.clear();
      try {
        Blockly.Xml.domToWorkspace(Blockly.utils.xml.textToDom(xml), workspace);
      } catch {
        // Fichier de programme refusé : on repart du programme de départ
        // plutôt que de laisser un état partiel dans l'éditeur.
        Blockly.Xml.domToWorkspace(
          Blockly.utils.xml.textToDom(defaultProgramXml()),
          workspace,
        );
      }
    } finally {
      loading = false;
    }
    publish();
  }

  function clear(): void {
    if (!workspace) return;
    loading = true;
    try {
      workspace.clear();
      Blockly.Xml.domToWorkspace(
        Blockly.utils.xml.textToDom(defaultProgramXml()),
        workspace,
      );
    } finally {
      loading = false;
    }
    publish();
  }

  /**
   * Recompile et renvoie l'état courant, sans dépendre des événements.
   *
   * On passe bien `workspace`, et non l'espace de noms `Blockly` : ce dernier
   * n'est pas un `Workspace`.
   */
  function refresh(): Program {
    if (!workspace) return { statements: [] };
    const result = compileWorkspace(workspace);
    onChange(result);
    return result.program;
  }

  function publish(): void {
    // Pendant un chargement, la compilation verrait des blocs à moitié
    // attachés. On attend la fin.
    if (loading) return;
    refresh();
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

  // Zoom : on passe par les méthodes de WorkspaceSvg plutôt que par un helper
  // global, plus simple à typer et à borner.
  const ZOOM_STEP = 1.2;
  const MIN_SCALE = 0.5;
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

    loading = true;
    try {
      Blockly.Xml.domToWorkspace(
        Blockly.utils.xml.textToDom(defaultProgramXml()),
        workspace,
      );
    } finally {
      loading = false;
    }

    registerApi({ serialize, load, clear, refresh });

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
    // les dimensions définitives sont connues.
    requestAnimationFrame(() => {
      requestAnimationFrame(applySize);
    });

    const listener = (event: Blockly.Events.Abstract) => {
      // Inutile de recompiler à chaque simple déplacement de bloc.
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
      Glisse un bloc et <strong>accroche-le</strong> sous un autre bloc.
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
        title="Remettre la taille normale"
        aria-label="Remettre la taille normale"
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

  /*
   * Largeur de la palette.
   *
   * Blockly dimensionne la palette d'après le contenu, mais la mesure se fait
   * alors que le moteur n'est pas encore prêt : il retient une largeur par
   * défaut d'environ 150 px. Nos blocs font jusqu'à 250 px (« Aller à gauche
   * pendant 5 secondes »), et étaient donc rognés — le texte et la flèche du
   * menu devenaient invisibles.
   *
   * On impose une largeur confortable, et on laisse la palette rétrécir si la
   * colonne devient étroite.
   */
  .editor__canvas :global(.blocklyFlyout) {
    min-width: 260px;
    max-width: 100%;
  }

  .editor__canvas :global(.blocklyFlyoutBackground) {
    width: 260px !important;
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