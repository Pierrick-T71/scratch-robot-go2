<script lang="ts">
  /**
   * Bibliothèque de blocs.
   *
   * Deux catégories seulement, parce qu'il n'existe que six blocs : afficher
   * des onglets vides (« Attente », « Capteurs »…) promettrait des fonctions
   * que le robot ne sait pas exécuter.
   *
   * Un bloc s'ajoute de deux façons : clic (simple) ou glisser-déposer.
   */
  import BlockTile from './BlockTile.svelte';
  import Icon from './Icon.svelte';
  import {
    BLOCKS,
    type PlayBlockKind,
    type PlayCategory,
  } from '../../lib/play/blocks';
  import { setDragPayload } from '../../lib/play/drag';

  interface Props {
    onAdd: (kind: PlayBlockKind) => void;
    onSettings?: () => void;
    onHelp?: () => void;
  }

  let { onAdd, onSettings, onHelp }: Props = $props();

  let category = $state<PlayCategory>('movement');

  const visible = $derived(BLOCKS.filter((spec) => spec.category === category));

  const TABS: ReadonlyArray<{ id: PlayCategory; label: string }> = [
    { id: 'movement', label: 'Mouvement' },
    { id: 'actions', label: 'Actions' },
  ];

  function dragStart(event: DragEvent, kind: PlayBlockKind): void {
    setDragPayload(event, { source: 'library', kind });
  }
</script>

<section class="library" aria-label="Bibliothèque de blocs">
  <header class="library__head">
    <h1 class="library__title">
      Bibliothèque de blocs
      <span class="library__sparkle" aria-hidden="true">
        <Icon name="sparkle" size={15} />
        <Icon name="sparkle" size={9} />
      </span>
    </h1>

    <nav class="tabs" aria-label="Catégories de blocs">
      {#each TABS as tab}
        <button
          type="button"
          class="tabs__tab"
          class:tabs__tab--active={category === tab.id}
          aria-pressed={category === tab.id}
          onclick={() => (category = tab.id)}
        >
          {tab.label}
        </button>
      {/each}
    </nav>
  </header>

  <div class="library__body">
    <div class="rail" aria-label="Raccourcis">
      <button
        type="button"
        class="rail__btn rail__btn--movement"
        class:rail__btn--active={category === 'movement'}
        aria-label="Blocs de mouvement"
        title="Mouvement"
        onclick={() => (category = 'movement')}
      >
        <Icon name="paw" size={22} />
      </button>
      <button
        type="button"
        class="rail__btn rail__btn--actions"
        class:rail__btn--active={category === 'actions'}
        aria-label="Blocs d’action"
        title="Actions"
        onclick={() => (category = 'actions')}
      >
        <Icon name="star" size={21} />
      </button>

      <span class="rail__gap"></span>

      <button
        type="button"
        class="rail__btn rail__btn--neutral"
        aria-label="Réglages du robot"
        title="Réglages"
        onclick={() => onSettings?.()}
      >
        <Icon name="settings" size={21} />
      </button>
      <button
        type="button"
        class="rail__btn rail__btn--neutral"
        aria-label="Aide"
        title="Aide"
        onclick={() => onHelp?.()}
      >
        <Icon name="help" size={21} />
      </button>
    </div>

    <div class="library__content">
      <div class="library__grid">
        {#each visible as spec (spec.kind)}
          <button
            type="button"
            class="slot"
            draggable="true"
            ondragstart={(event) => dragStart(event, spec.kind)}
            onclick={() => onAdd(spec.kind)}
            title={`Ajouter « ${spec.label} » au programme`}
          >
            <BlockTile kind={spec.kind} />
          </button>
        {/each}
      </div>

      <p class="library__hint">
        Clique sur un bloc pour l’ajouter, ou glisse-le dans
        <strong>Mon Programme</strong>.
      </p>
    </div>
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
    gap: 18px;
    flex-wrap: wrap;
    padding-bottom: 12px;
    border-bottom: 1px solid #303543;
  }

  .library__title {
    display: inline-flex;
    align-items: center;
    gap: 9px;
    margin: 0;
    font-size: 17px;
    font-weight: 650;
    letter-spacing: 0.02em;
    color: #b9c1d2;
    text-transform: uppercase;
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

  .tabs {
    display: flex;
    align-items: center;
    gap: 6px;
    margin-left: auto;
    flex-wrap: wrap;
  }

  .tabs__tab {
    padding: 8px 16px;
    border: 1px solid transparent;
    border-radius: 999px;
    background: transparent;
    font-family: inherit;
    font-size: 18px;
    font-weight: 600;
    color: #98a1b3;
    cursor: pointer;
    transition:
      background 0.15s ease,
      color 0.15s ease,
      border-color 0.15s ease;
  }

  .tabs__tab:hover {
    color: #e6ebf5;
    background: #2b2f3b;
  }

  .tabs__tab--active {
    color: #f1f4fa;
    background: #2f3442;
    border-color: #3d4454;
    box-shadow: inset 0 1px 0 rgb(255 255 255 / 6%);
  }

  .tabs__tab:focus-visible {
    outline: 2px solid #7fa8dd;
    outline-offset: 2px;
  }

  .library__body {
    display: flex;
    gap: 18px;
    flex: 1;
    min-height: 0;
    padding-top: 14px;
  }

  .rail {
    display: flex;
    flex-direction: column;
    gap: 10px;
    flex: none;
    padding-top: 4px;
  }

  .rail__gap {
    flex: 1;
    min-height: 12px;
  }

  .rail__btn {
    display: grid;
    place-items: center;
    width: 46px;
    height: 46px;
    border: 1px solid transparent;
    border-radius: 50%;
    background: transparent;
    color: #7f8899;
    cursor: pointer;
    transition:
      background 0.15s ease,
      color 0.15s ease,
      transform 0.12s ease;
  }

  .rail__btn:hover {
    transform: translateY(-1px);
    background: #2c313d;
    color: #dfe5f0;
  }

  .rail__btn:focus-visible {
    outline: 2px solid #7fa8dd;
    outline-offset: 2px;
  }

  .rail__btn--active.rail__btn--movement {
    background: #2b4a6d;
    color: #a8cdf3;
    box-shadow:
      inset 0 0 0 1px #3c6490,
      0 6px 14px rgb(0 0 0 / 25%);
  }

  .rail__btn--active.rail__btn--actions {
    background: #523528;
    color: #f7c6a9;
    box-shadow:
      inset 0 0 0 1px #75503d,
      0 6px 14px rgb(0 0 0 / 25%);
  }

  .rail__btn--neutral {
    width: 42px;
    height: 42px;
    color: #6f7889;
  }

  .library__content {
    display: flex;
    flex-direction: column;
    flex: 1;
    min-width: 0;
    min-height: 0;
    overflow-y: auto;
    padding-right: 4px;
  }

  .library__grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
    gap: 22px 18px;
    align-content: start;
  }

  .slot {
    display: block;
    padding: 0;
    border: 0;
    background: transparent;
    text-align: left;
    font: inherit;
    border-radius: 15px;
    cursor: pointer;
  }

  .slot:focus-visible {
    outline: 3px solid #9fc4ec;
    outline-offset: 4px;
  }

  .library__hint {
    margin: auto 0 0;
    padding-top: 18px;
    font-size: 12.5px;
    color: #7c8598;
  }

  .library__hint strong {
    color: #a9b2c4;
    font-weight: 700;
  }

  @media (max-width: 720px) {
    .library__title {
      font-size: 14px;
    }

    .tabs__tab {
      font-size: 15px;
      padding: 7px 12px;
    }

    .library__body {
      gap: 10px;
    }

    .rail__btn {
      width: 40px;
      height: 40px;
    }
  }
</style>
