<script lang="ts">
  /**
   * « Mon Programme » — la timeline horizontale.
   *
   * L'ordre visuel EST l'ordre d'exécution. Les blocs se glissent depuis la
   * bibliothèque, se réordonnent par glisser-déposer, et se retirent par leur
   * croix. Pendant l'exécution, le bloc courant s'illumine.
   */
  import BlockTile from './BlockTile.svelte';
  import Icon from './Icon.svelte';
  import type { PlayBlock, PlayBlockKind } from '../../lib/play/blocks';
  import { readDragPayload, setDragPayload } from '../../lib/play/drag';
  import type { AppNotice } from '../../lib/stores/app.svelte';

  interface Props {
    blocks: readonly PlayBlock[];
    /** Index du bloc en cours d'exécution, ou null. */
    runningIndex: number | null;
    busy: boolean;
    notice: AppNotice | null;
    onAdd: (kind: PlayBlockKind, index?: number) => void;
    onRemove: (id: string) => void;
    onChangeSeconds: (id: string, seconds: number) => void;
    onChangeDegrees: (id: string, degrees: number) => void;
    onMove: (id: string, toIndex: number) => void;
    onStart: () => void;
    onClear: () => void;
  }

  let {
    blocks,
    runningIndex,
    busy,
    notice,
    onAdd,
    onRemove,
    onChangeSeconds,
    onChangeDegrees,
    onMove,
    onStart,
    onClear,
  }: Props = $props();

  let stripEl = $state<HTMLDivElement | undefined>();
  let insertion = $state<number | null>(null);
  let dragging = $state<string | null>(null);

  /** Position d'insertion d'après le doigt / la souris. */
  function indexAt(clientX: number): number {
    if (!stripEl) return blocks.length;
    const cards = Array.from(
      stripEl.querySelectorAll<HTMLElement>('[data-index]'),
    );
    for (const card of cards) {
      const rect = card.getBoundingClientRect();
      if (clientX < rect.left + rect.width / 2) {
        return Number(card.dataset.index);
      }
    }
    return blocks.length;
  }

  function startDrag(event: DragEvent, block: PlayBlock): void {
    dragging = block.id;
    setDragPayload(event, { source: 'timeline', id: block.id });
  }

  function endDrag(): void {
    dragging = null;
    insertion = null;
  }

  function over(event: DragEvent): void {
    event.preventDefault();
    if (event.dataTransfer) {
      event.dataTransfer.dropEffect = dragging ? 'move' : 'copy';
    }
    insertion = indexAt(event.clientX);
  }

  function leave(event: DragEvent): void {
    const target = event.currentTarget as HTMLElement;
    if (!target.contains(event.relatedTarget as Node | null)) {
      insertion = null;
    }
  }

  function drop(event: DragEvent): void {
    event.preventDefault();
    const payload = readDragPayload(event);
    const target = insertion ?? indexAt(event.clientX);
    insertion = null;
    dragging = null;
    if (!payload) return;
    if (payload.source === 'library') onAdd(payload.kind, target);
    else onMove(payload.id, target);
  }
</script>

<section class="program" aria-label="Mon programme">
  <header class="program__head">
    <h2 class="program__title">
      Mon Programme
      <span class="program__sparkle" aria-hidden="true">
        <Icon name="sparkle" size={15} />
        <Icon name="sparkle" size={9} />
      </span>
    </h2>

    <div class="program__tools">
      {#if notice}
        <p class="notice notice--{notice.tone}" role="status" title={notice.message}>
          {notice.message}
        </p>
      {/if}

      <button
        type="button"
        class="tool"
        aria-label="Tout effacer"
        title="Tout effacer"
        disabled={busy || blocks.length === 0}
        onclick={onClear}
      >
        <Icon name="trash" size={19} />
      </button>

      <button
        type="button"
        class="flag"
        class:flag--busy={busy}
        aria-label="Lancer le programme"
        title="Lancer le programme"
        disabled={busy || blocks.length === 0}
        onclick={onStart}
      >
        <Icon name="flag" size={22} />
      </button>
    </div>
  </header>

  <!-- Zone de dépôt : le glisser-déposer est un raccourci pour la souris ;
       les boutons de la bibliothèque restent la voie accessible. -->
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div
    class="timeline"
    ondragover={over}
    ondragleave={leave}
    ondrop={drop}
  >
    <div
      class="dropzone"
      class:dropzone--over={insertion !== null && blocks.length === 0}
    >
      <span class="dropzone__hand" aria-hidden="true">
        <Icon name="hand" size={28} />
      </span>
      <p class="dropzone__text">
        Glisser-déposer les blocs<br />ici pour programmer
      </p>
      <span class="dropzone__hand" aria-hidden="true">
        <Icon name="hand" size={28} />
      </span>
    </div>

    <div
      class="strip"
      role="list"
      aria-label="Blocs du programme, dans l’ordre d’exécution"
      bind:this={stripEl}
    >
      {#each blocks as block, index (block.id)}
        {#if insertion === index}
          <span class="caret" aria-hidden="true"></span>
        {/if}

        <!-- Réordonner au doigt ou à la souris. Le clavier garde la main sur
             l'ajout (bibliothèque) et la suppression (croix du bloc). -->
        <!-- svelte-ignore a11y_no_static_element_interactions -->
        <div
          class="card"
          class:card--dragging={dragging === block.id}
          role="listitem"
          data-index={index}
          draggable={!busy}
          ondragstart={(event) => startDrag(event, block)}
          ondragend={endDrag}
        >
          <BlockTile
            kind={block.kind}
            seconds={block.seconds}
            degrees={block.degrees}
            editable={!busy}
            removable={!busy}
            running={runningIndex === index}
            onRemove={() => onRemove(block.id)}
            onSecondsChange={(value) => onChangeSeconds(block.id, value)}
            onDegreesChange={(value) => onChangeDegrees(block.id, value)}
          />
        </div>

        {#if index < blocks.length - 1}
          <span class="link" aria-hidden="true">›</span>
        {/if}
      {/each}

      {#if insertion === blocks.length && blocks.length > 0}
        <span class="caret" aria-hidden="true"></span>
      {/if}
    </div>
  </div>
</section>

<style>
  .program {
    display: flex;
    flex-direction: column;
    min-width: 0;
    padding: 14px 18px 16px;
    background: #242731;
    border: 1px solid #2f3441;
    border-radius: 22px;
    box-shadow:
      inset 0 1px 0 rgb(255 255 255 / 4%),
      0 18px 40px rgb(0 0 0 / 25%);
  }

  .program__head {
    display: flex;
    align-items: center;
    gap: 14px;
    min-height: 44px;
  }

  .program__title {
    display: inline-flex;
    align-items: center;
    gap: 9px;
    margin: 0;
    font-size: 19px;
    font-weight: 700;
    letter-spacing: -0.01em;
    color: #e8edf7;
  }

  .program__sparkle {
    display: inline-flex;
    align-items: flex-end;
    gap: 2px;
    color: #c3a4f2;
  }

  .program__sparkle :global(svg:last-child) {
    color: #8fb7ea;
    transform: translateY(-3px);
  }

  .program__tools {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-left: auto;
    min-width: 0;
  }

  .notice {
    margin: 0;
    padding: 7px 13px;
    border-radius: 999px;
    font-size: 13px;
    font-weight: 650;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 46ch;
  }

  .notice--ok {
    background: #17331f;
    color: #8fe0a8;
    border: 1px solid #2c5b3b;
  }

  .notice--warn {
    background: #332910;
    color: #f3c96b;
    border: 1px solid #5c4a1d;
  }

  .notice--error {
    background: #3a1c20;
    color: #f4a3ad;
    border: 1px solid #6b3038;
  }

  .tool {
    display: grid;
    place-items: center;
    width: 38px;
    height: 38px;
    border: 1px solid #353b49;
    border-radius: 12px;
    background: #2a2e39;
    color: #9aa3b5;
    cursor: pointer;
    transition:
      background 0.15s ease,
      color 0.15s ease;
  }

  .tool:hover:not(:disabled) {
    background: #343a48;
    color: #e7ecf5;
  }

  .tool:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }

  .tool:focus-visible,
  .flag:focus-visible {
    outline: 2px solid #9fc4ec;
    outline-offset: 2px;
  }

  .flag {
    display: grid;
    place-items: center;
    width: 46px;
    height: 46px;
    border: 1px solid #3f8f5c;
    border-radius: 14px;
    background: linear-gradient(180deg, #3fbf72, #2f9d5c);
    color: #f3fff7;
    cursor: pointer;
    box-shadow:
      inset 0 1px 0 rgb(255 255 255 / 30%),
      0 8px 20px rgb(47 157 92 / 35%);
    transition:
      transform 0.13s ease,
      filter 0.15s ease;
  }

  .flag:hover:not(:disabled) {
    transform: translateY(-1px);
    filter: brightness(1.06);
  }

  .flag:active:not(:disabled) {
    transform: translateY(0);
  }

  .flag:disabled {
    opacity: 0.4;
    cursor: not-allowed;
    box-shadow: none;
  }

  .flag--busy {
    animation: pulse-flag 1.5s ease-in-out infinite;
  }

  @keyframes pulse-flag {
    0%,
    100% {
      filter: brightness(1);
    }
    50% {
      filter: brightness(1.18);
    }
  }

  .timeline {
    display: flex;
    align-items: stretch;
    gap: 14px;
    min-height: 0;
    margin-top: 10px;
  }

  .dropzone {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 16px;
    flex: none;
    width: clamp(260px, 38%, 460px);
    min-height: 154px;
    padding: 14px 18px;
    border: 2px dashed #3c4353;
    border-radius: 20px;
    background: rgb(255 255 255 / 1.5%);
    color: #7f8899;
    transition:
      border-color 0.15s ease,
      background 0.15s ease,
      color 0.15s ease;
  }

  .dropzone--over {
    border-color: #7fa8dd;
    background: rgb(127 168 221 / 10%);
    color: #cfe3f8;
  }

  .dropzone__text {
    margin: 0;
    font-size: 20px;
    font-weight: 500;
    line-height: 1.35;
    text-align: center;
    letter-spacing: -0.01em;
  }

  .dropzone__hand {
    color: #6e7789;
    opacity: 0.9;
  }

  .strip {
    display: flex;
    align-items: center;
    gap: 12px;
    flex: 1;
    min-width: 0;
    padding: 22px 8px 18px;
    overflow-x: auto;
    overflow-y: hidden;
    scrollbar-width: thin;
    scrollbar-color: #3f4657 transparent;
  }

  .strip::-webkit-scrollbar {
    height: 10px;
  }

  .strip::-webkit-scrollbar-track {
    background: transparent;
  }

  .strip::-webkit-scrollbar-thumb {
    background: #3f4657;
    border-radius: 999px;
  }

  .card {
    flex: none;
    border-radius: 15px;
    cursor: grab;
  }

  .card:active {
    cursor: grabbing;
  }

  .card--dragging {
    opacity: 0.45;
  }

  .link {
    flex: none;
    color: #6f7889;
    font-size: 26px;
    font-weight: 700;
    line-height: 1;
  }

  .caret {
    flex: none;
    width: 4px;
    height: 78px;
    border-radius: 999px;
    background: #9fc4ec;
    box-shadow: 0 0 14px rgb(159 196 236 / 70%);
    animation: blink 0.9s ease-in-out infinite;
  }

  @keyframes blink {
    0%,
    100% {
      opacity: 1;
    }
    50% {
      opacity: 0.35;
    }
  }

  @media (max-width: 980px) {
    .dropzone {
      width: 240px;
    }

    .dropzone__text {
      font-size: 16px;
    }

    .dropzone__hand {
      display: none;
    }
  }

  @media (max-width: 720px) {
    .timeline {
      flex-direction: column;
    }

    .dropzone {
      width: 100%;
      min-height: 84px;
    }

    .strip {
      padding-top: 8px;
    }
  }

  @media (prefers-reduced-motion: reduce) {
    .flag--busy,
    .caret {
      animation: none;
    }
  }
</style>
