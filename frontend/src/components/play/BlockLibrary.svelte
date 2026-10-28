<script lang="ts">
  /**
   * Bibliothèque de blocs pour Optimus.
   *
   * Deux catégories claires (« Mouvements » et « Actions ») plus une vue d'ensemble,
   * pensées pour être ergonomiques et immédiates pour des enfants.
   *
   * Un bloc s'ajoute au clic ou par glisser-déposer vers Mon Programme.
   */
  import BlockTile from './BlockTile.svelte';
  import Icon from './Icon.svelte';
  import {
    BLOCKS,
    type PlayBlockKind,
    type PlayCategory,
  } from '../../lib/play/blocks';
  import { dragSession, readDragPayload, setDragPayload } from '../../lib/play/drag';

  interface Props {
    onAdd: (kind: PlayBlockKind) => void;
    onRemove?: (id: string) => void;
    onSettings?: () => void;
    onHelp?: () => void;
  }

  let { onAdd, onRemove, onSettings, onHelp }: Props = $props();

  type LibraryFilter = 'all' | PlayCategory;
  let category = $state<LibraryFilter>('movement');
  let isOverLibrary = $state(false);

  const isDraggingTimeline = $derived(dragSession.current?.source === 'timeline');

  const visible = $derived(
    category === 'all'
      ? BLOCKS
      : BLOCKS.filter((spec) => spec.category === category),
  );

  const movementCount = $derived(BLOCKS.filter((s) => s.category === 'movement').length);
  const actionsCount = $derived(BLOCKS.filter((s) => s.category === 'actions').length);

  function dragStart(event: DragEvent, kind: PlayBlockKind): void {
    setDragPayload(event, { source: 'library', kind });
  }

  function handleDragOver(event: DragEvent): void {
    if (!isDraggingTimeline) return;
    event.preventDefault();
    if (event.dataTransfer) {
      event.dataTransfer.dropEffect = 'move';
    }
    isOverLibrary = true;
  }

  function handleDragLeave(event: DragEvent): void {
    const target = event.currentTarget as HTMLElement;
    if (!target.contains(event.relatedTarget as Node | null)) {
      isOverLibrary = false;
    }
  }

  function handleDrop(event: DragEvent): void {
    if (!isDraggingTimeline) return;
    event.preventDefault();
    event.stopPropagation();
    const payload = readDragPayload(event);
    if (payload && payload.source === 'timeline') {
      onRemove?.(payload.id);
    }
    isOverLibrary = false;
    dragSession.end();
  }
</script>

<section
  class="library"
  class:library--delete-active={isDraggingTimeline}
  class:library--delete-hover={isOverLibrary}
  aria-label="Bibliothèque de blocs"
  ondragover={handleDragOver}
  ondragleave={handleDragLeave}
  ondrop={handleDrop}
>
  <header class="library__head">
    <h2 class="library__title">
      Bibliothèque de blocs
      <span class="library__sparkle" aria-hidden="true">
        <Icon name="sparkle" size={15} />
        <Icon name="sparkle" size={9} />
      </span>
    </h2>

    <div class="library__tools">
      <button
        type="button"
        class="lib-tool"
        aria-label="Réglages du robot"
        title="Réglages"
        onclick={() => onSettings?.()}
      >
        <Icon name="settings" size={20} />
      </button>
      <button
        type="button"
        class="lib-tool lib-tool--help"
        aria-label="Guide d'aide"
        title="Guide d'aide"
        onclick={() => onHelp?.()}
      >
        <Icon name="help" size={18} />
        <span class="lib-tool__label">Aide</span>
      </button>
    </div>
  </header>

  <!-- Sélecteur de catégories simplifié et ergonomique pour enfants -->
  <div class="cat-bar" role="tablist" aria-label="Catégories de blocs">
    <button
      type="button"
      role="tab"
      class="cat-pill cat-pill--movement"
      class:cat-pill--active={category === 'movement'}
      aria-selected={category === 'movement'}
      onclick={() => (category = 'movement')}
    >
      <span class="cat-pill__icon" aria-hidden="true">
        <Icon name="paw" size={19} />
      </span>
      <span class="cat-pill__label">Mouvements</span>
      <span class="cat-pill__count">{movementCount}</span>
    </button>

    <button
      type="button"
      role="tab"
      class="cat-pill cat-pill--actions"
      class:cat-pill--active={category === 'actions'}
      aria-selected={category === 'actions'}
      onclick={() => (category = 'actions')}
    >
      <span class="cat-pill__icon" aria-hidden="true">
        <Icon name="star" size={19} />
      </span>
      <span class="cat-pill__label">Actions</span>
      <span class="cat-pill__count">{actionsCount}</span>
    </button>

    <button
      type="button"
      role="tab"
      class="cat-pill cat-pill--all"
      class:cat-pill--active={category === 'all'}
      aria-selected={category === 'all'}
      onclick={() => (category = 'all')}
    >
      <span class="cat-pill__icon" aria-hidden="true">
        <Icon name="sparkle" size={17} />
      </span>
      <span class="cat-pill__label">Tous les blocs</span>
      <span class="cat-pill__count">{BLOCKS.length}</span>
    </button>
  </div>

  <div class="library__content">
    <div class="library__grid">
      {#each visible as spec (spec.kind)}
        <button
          type="button"
          class="slot"
          draggable={!isDraggingTimeline}
          ondragstart={(event) => dragStart(event, spec.kind)}
          onclick={() => onAdd(spec.kind)}
          title={isDraggingTimeline
            ? 'Relâcher pour supprimer ce bloc'
            : `Cliquer ou glisser pour ajouter « ${spec.label} »`}
        >
          <BlockTile kind={spec.kind} />
        </button>
      {/each}
    </div>

    {#if isDraggingTimeline}
      <!-- Zone de suppression discrète à la place de l'astuce (gain de place vertical) -->
      <div
        class="lib-delete-hint"
        class:lib-delete-hint--over={isOverLibrary}
        role="status"
      >
        <span class="lib-delete-hint__icon" aria-hidden="true">
          <Icon name="trash" size={18} />
        </span>
        <span class="lib-delete-hint__text">
          {isOverLibrary
            ? 'Relâcher pour supprimer'
            : 'Glisser ici pour supprimer'}
        </span>
      </div>
    {:else}
      <p class="library__hint">
        💡 <strong>Astuce :</strong> Clique sur un bloc pour l’ajouter, ou glisse-le dans <strong>Mon Programme</strong>.
      </p>
    {/if}
  </div>
</section>

<style>
  .library {
    display: flex;
    flex-direction: column;
    min-width: 0;
    min-height: 0;
    padding: 14px 18px 12px;
    background: #242731;
    border: 1px solid #2f3441;
    border-radius: 22px;
    box-shadow:
      inset 0 1px 0 rgb(255 255 255 / 4%),
      0 18px 40px rgb(0 0 0 / 25%);
    overflow: hidden;
  }

  .library__head {
    display: flex;
    align-items: center;
    gap: 14px;
    padding-bottom: 12px;
    border-bottom: 1px solid #303543;
  }

  .library__title {
    display: inline-flex;
    align-items: center;
    gap: 9px;
    margin: 0;
    font-size: 17px;
    font-weight: 700;
    letter-spacing: 0.01em;
    color: #e4e9f5;
  }

  .library__sparkle {
    position: relative;
    display: inline-flex;
    align-items: flex-end;
    gap: 2px;
    color: #c3a4f2;
  }

  .library__sparkle :global(svg:last-child) {
    color: #8fb7ea;
    transform: translateY(-3px);
  }

  .library__tools {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-left: auto;
  }

  .lib-tool {
    display: grid;
    place-items: center;
    width: 38px;
    height: 38px;
    border: 1px solid #363c4c;
    border-radius: 12px;
    background: #272b36;
    color: #8c96a8;
    cursor: pointer;
    transition:
      background 0.15s ease,
      color 0.15s ease,
      transform 0.12s ease;
  }

  .lib-tool--help {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    width: auto;
    padding: 0 12px;
    font-size: 13.5px;
    font-weight: 700;
  }

  .lib-tool:hover {
    background: #333948;
    color: #e7ecf6;
    transform: translateY(-1px);
  }

  .lib-tool:focus-visible {
    outline: 2px solid #7fa8dd;
    outline-offset: 2px;
  }

  /* Barre de sélection ergonomique pour enfants */
  .cat-bar {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 12px 0 12px;
    border-bottom: 1px solid #2d323f;
    flex-wrap: wrap;
  }

  .cat-pill {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 8px 16px;
    border: 1.5px solid #363c4c;
    border-radius: 999px;
    background: #272b36;
    color: #9aa3b5;
    font-family: inherit;
    font-size: 15px;
    font-weight: 700;
    cursor: pointer;
    transition:
      background 0.15s ease,
      color 0.15s ease,
      border-color 0.15s ease,
      transform 0.12s ease,
      box-shadow 0.15s ease;
  }

  .cat-pill:hover {
    color: #f0f3fa;
    border-color: #4f576d;
    background: #2e3442;
    transform: translateY(-1px);
  }

  .cat-pill:focus-visible {
    outline: 2px solid #7fa8dd;
    outline-offset: 2px;
  }

  .cat-pill__icon {
    display: grid;
    place-items: center;
    line-height: 1;
  }

  .cat-pill__label {
    letter-spacing: -0.01em;
  }

  .cat-pill__count {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: 20px;
    height: 20px;
    padding: 0 6px;
    border-radius: 999px;
    background: rgb(255 255 255 / 10%);
    font-size: 12px;
    font-weight: 800;
  }

  .cat-pill--active.cat-pill--movement {
    color: #e3effc;
    background: #1e3a5f;
    border-color: #3b6b9e;
    box-shadow: 0 4px 12px rgb(30 58 95 / 40%);
  }

  .cat-pill--active.cat-pill--actions {
    color: #fdeee5;
    background: #543324;
    border-color: #8c583f;
    box-shadow: 0 4px 12px rgb(84 51 36 / 40%);
  }

  .cat-pill--active.cat-pill--all {
    color: #f5edfd;
    background: #422d5c;
    border-color: #6e4c96;
    box-shadow: 0 4px 12px rgb(66 45 92 / 40%);
  }

  .cat-pill--active .cat-pill__count {
    background: rgb(255 255 255 / 22%);
    color: #fff;
  }

  .library__content {
    display: flex;
    flex-direction: column;
    flex: 1;
    min-width: 0;
    min-height: 0;
    overflow-y: auto;
    overflow-x: hidden;
    padding: 14px 8px 12px 2px;
  }

  .library__grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(134px, 1fr));
    gap: 26px 20px;
    align-content: start;
    justify-items: center;
    padding-bottom: 12px;
  }

  .slot {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 124px;
    height: 124px;
    padding: 0;
    border: 0;
    background: transparent;
    text-align: center;
    font: inherit;
    border-radius: 16px;
    cursor: pointer;
    position: relative;
  }

  .slot:hover :global(.blk) {
    transform: translateY(-2px);
  }

  .slot:focus-visible {
    outline: 3px solid #9fc4ec;
    outline-offset: 4px;
  }

  .library--delete-active {
    border-color: #3f475a;
  }

  .library--delete-hover {
    border-color: #e0596b;
  }

  .lib-delete-hint {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    width: 100%;
    max-width: 100%;
    box-sizing: border-box;
    margin: auto 0 0;
    padding: 8px 12px;
    border: 1.5px dashed #e0596b;
    border-radius: 12px;
    background: rgba(224, 89, 107, 0.15);
    color: #ff9ea9;
    font-size: 13px;
    font-weight: 750;
    line-height: 1.25;
    text-align: center;
    transition: background 0.15s ease, border-color 0.15s ease, color 0.15s ease;
  }

  .lib-delete-hint--over {
    border-color: #ff3850;
    background: rgba(224, 89, 107, 0.34);
    color: #ffffff;
    box-shadow: 0 0 16px rgba(224, 89, 107, 0.45);
  }

  .lib-delete-hint__icon {
    display: grid;
    place-items: center;
    color: #ff5e73;
    flex: none;
  }

  .lib-delete-hint--over .lib-delete-hint__icon {
    color: #ffffff;
    transform: scale(1.12);
  }

  .lib-delete-hint__text {
    min-width: 0;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .library__hint {
    margin: auto 0 0;
    padding-top: 14px;
    font-size: 13px;
    color: #8a93a5;
  }

  .library__hint strong {
    color: #c0c8da;
    font-weight: 700;
  }

  @media (max-width: 720px) {
    .library__title {
      font-size: 15px;
    }

    .cat-pill {
      font-size: 14px;
      padding: 6px 12px;
    }

    .library__grid {
      grid-template-columns: repeat(auto-fill, minmax(96px, 1fr));
      gap: 12px 10px;
    }
  }

  /* Grands écrans de PC fixe (au-delà de 20 pouces, >= 1700px pour ne pas impacter les portables 15" à 1536px) */
  @media (min-width: 1700px) {
    .library__title {
      font-size: 19px;
    }

    .cat-pill {
      font-size: 15.5px;
      padding: 9px 18px;
    }

    .library__grid {
      grid-template-columns: repeat(auto-fill, minmax(158px, 1fr));
      gap: 28px 24px;
    }

    .slot {
      width: 146px;
      height: 146px;
    }
  }

  /* Très grands écrans (27 pouces et plus / QHD / 4K, >= 2200px) */
  @media (min-width: 2200px) {
    .library__title {
      font-size: 21px;
    }

    .cat-pill {
      font-size: 17px;
      padding: 10px 20px;
    }

    .library__grid {
      grid-template-columns: repeat(auto-fill, minmax(172px, 1fr));
      gap: 32px 28px;
    }

    .slot {
      width: 158px;
      height: 158px;
    }
  }
</style>
