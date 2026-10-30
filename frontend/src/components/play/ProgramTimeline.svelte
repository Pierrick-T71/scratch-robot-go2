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
  import { dragSession, readDragPayload, setDragPayload } from '../../lib/play/drag';
  import type { AppNotice } from '../../lib/stores/app.svelte';

  interface Props {
    blocks: readonly PlayBlock[];
    /** Index du bloc en cours d'exécution, ou null. */
    runningIndex: number | null;
    busy: boolean;
    /** Le robot est verrouillé par la sécurité : on ne peut pas relancer. */
    blocked?: boolean;
    autonomousActive?: boolean;
    notice: AppNotice | null;
    onAdd: (kind: PlayBlockKind, index?: number) => void;
    onRemove: (id: string) => void;
    onChangeSeconds: (id: string, seconds: number) => void;
    onChangeDegrees: (id: string, degrees: number) => void;
    onMove: (id: string, toIndex: number) => void;
    onStart: () => void;
    onStop: () => void;
    onClear: () => void;
    onImportFile?: (file: File) => void;
    onChooseFile?: () => void;
  }

  let {
    blocks,
    runningIndex,
    busy,
    blocked = false,
    autonomousActive = false,
    notice,
    onAdd,
    onRemove,
    onChangeSeconds,
    onChangeDegrees,
    onMove,
    onStart,
    onStop,
    onClear,
    onImportFile,
    onChooseFile,
  }: Props = $props();

  let stripEl = $state<HTMLDivElement | undefined>();
  let insertion = $state<number | null>(null);
  let dragging = $state<string | null>(null);
  let overDropzone = $state(false);
  let overTrashTool = $state(false);

  const isDraggingTimeline = $derived(
    dragging !== null || dragSession.current?.source === 'timeline',
  );

  $effect(() => {
    const handleWindowDragEnd = () => endDrag();
    window.addEventListener('dragend', handleWindowDragEnd);
    return () => {
      window.removeEventListener('dragend', handleWindowDragEnd);
    };
  });

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
    const target = event.target as HTMLElement | null;
    if (target?.closest('select') || target?.closest('.blk__pill--edit')) {
      event.preventDefault();
      return;
    }
    dragging = block.id;
    dragSession.start({ source: 'timeline', id: block.id });
    setDragPayload(event, { source: 'timeline', id: block.id });
  }

  function endDrag(): void {
    dragging = null;
    insertion = null;
    overDropzone = false;
    overTrashTool = false;
    dragSession.end();
  }

  function over(event: DragEvent): void {
    event.preventDefault();
    if (event.dataTransfer) {
      const isFile = Array.from(event.dataTransfer.types || []).includes('Files');
      event.dataTransfer.dropEffect = isFile || !isDraggingTimeline ? 'copy' : 'move';
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
    const target = insertion;
    insertion = null;
    dragging = null;
    overDropzone = false;
    overTrashTool = false;
    dragSession.end();

    // Glisser-déposer d'un fichier JSON externe
    const files = event.dataTransfer?.files;
    if (files && files.length > 0) {
      const file = files[0];
      if (file) onImportFile?.(file);
      return;
    }

    const payload = readDragPayload(event);
    if (!payload) return;

    if (payload.source === 'library') {
      onAdd(payload.kind, target ?? blocks.length);
    } else if (payload.source === 'timeline') {
      if (target !== null) {
        onMove(payload.id, target);
      } else {
        // Lâché hors de l'alignement des blocs (« bouger ailleurs ») -> suppression
        onRemove(payload.id);
      }
    }
  }

  function handleDropzoneDrop(event: DragEvent): void {
    event.preventDefault();
    event.stopPropagation();
    const payload = readDragPayload(event);
    overDropzone = false;
    endDrag();

    const files = event.dataTransfer?.files;
    if (files && files.length > 0) {
      const file = files[0];
      if (file) onImportFile?.(file);
      return;
    }

    if (payload && payload.source === 'timeline') {
      onRemove(payload.id);
    }
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
        class:tool--drop-target={isDraggingTimeline}
        class:tool--drop-hover={overTrashTool}
        aria-label="Tout effacer"
        title={isDraggingTimeline ? "Déposer ici pour supprimer le bloc" : "Tout effacer"}
        disabled={!isDraggingTimeline && (busy || blocks.length === 0)}
        onclick={onClear}
        ondragover={(e) => {
          if (isDraggingTimeline) {
            e.preventDefault();
            overTrashTool = true;
          }
        }}
        ondragleave={() => (overTrashTool = false)}
        ondrop={(e) => {
          e.preventDefault();
          e.stopPropagation();
          const payload = readDragPayload(e);
          if (payload && payload.source === 'timeline') {
            onRemove(payload.id);
          }
          overTrashTool = false;
          endDrag();
        }}
      >
        <Icon name="trash" size={19} />
      </button>

      <button
        type="button"
        class="flag"
        class:flag--busy={busy}
        aria-label="Lancer le programme"
        title={blocked
          ? 'Repose le robot au sol et attends qu’il soit stable avant de relancer'
          : 'Lancer le programme'}
        disabled={busy || blocks.length === 0 || blocked}
        onclick={onStart}
      >
        <Icon name="flag" size={22} />
      </button>

      <button
        type="button"
        class="stop-btn"
        class:stop-btn--active={busy || autonomousActive}
        aria-label="Arrêter le robot ou le programme"
        title={busy || autonomousActive
          ? 'Arrêter immédiatement le robot ou le programme en cours'
          : 'Aucune action en cours à arrêter'}
        disabled={!busy && !autonomousActive}
        onclick={onStop}
      >
        <Icon name="stop" size={20} />
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
    <!-- svelte-ignore a11y_click_events_have_key_events -->
    <div
      class="dropzone"
      class:dropzone--over={insertion !== null && blocks.length === 0}
      class:dropzone--delete={isDraggingTimeline}
      class:dropzone--delete-over={overDropzone}
      role="button"
      tabindex="0"
      onclick={onChooseFile}
      onkeydown={(e) => (e.key === 'Enter' || e.key === ' ') && onChooseFile?.()}
      ondragover={(e) => {
        e.preventDefault();
        if (isDraggingTimeline) {
          overDropzone = true;
          if (e.dataTransfer) e.dataTransfer.dropEffect = 'move';
        }
      }}
      ondragleave={() => {
        overDropzone = false;
      }}
      ondrop={handleDropzoneDrop}
      title={isDraggingTimeline
        ? 'Relâcher ici pour supprimer ce bloc'
        : 'Cliquer pour choisir un fichier programme JSON, ou glisser-déposer un fichier ou des blocs ici'}
    >
      <span class="dropzone__icon" aria-hidden="true">
        <Icon name={isDraggingTimeline ? 'trash' : 'upload'} size={isDraggingTimeline ? 22 : 18} />
      </span>
      <p class="dropzone__text">
        {#if isDraggingTimeline}
          <strong>{overDropzone ? 'Relâcher pour supprimer' : 'Glisser ici pour supprimer'}</strong>
        {:else}
          Glisser-déposer le fichier ou les blocs ici pour programmer
        {/if}
      </p>
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
             l'ajout (bibliothèque). -->
        <!-- svelte-ignore a11y_no_static_element_interactions -->
        <div
          class="card"
          class:card--dragging={dragging === block.id}
          role="listitem"
          data-index={index}
          style="z-index: {blocks.length - index};"
          draggable={!busy}
          ondragstart={(event) => startDrag(event, block)}
          ondragend={endDrag}
        >
          <BlockTile
            kind={block.kind}
            seconds={block.seconds}
            degrees={block.degrees}
            editable={!busy}
            running={runningIndex === index}
            puzzle={true}
            isFirst={index === 0}
            isLast={index === blocks.length - 1}
            onSecondsChange={(value) => onChangeSeconds(block.id, value)}
            onDegreesChange={(value) => onChangeDegrees(block.id, value)}
          />
        </div>
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
    overflow-x: hidden;
    padding: 10px 18px 10px;
    background: #242731;
    border: 1px solid #2f3441;
    border-radius: 22px;
    box-shadow:
      inset 0 1px 0 rgb(255 255 255 / 4%),
      0 18px 40px rgb(0 0 0 / 25%);
  }

  .program__head {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 14px;
    min-height: 38px;
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
    flex-wrap: wrap;
    align-items: center;
    justify-content: flex-end;
    gap: 10px;
    margin-left: auto;
    min-width: 0;
  }

  .notice {
    flex: 0 1 auto;
    min-width: 0;
    max-width: min(52ch, 100%);
    margin: 0;
    padding: 7px 13px;
    border-radius: 14px;
    font-size: 13px;
    font-weight: 650;
    line-height: 1.35;
    text-align: left;
    white-space: normal;
    overflow-wrap: anywhere;
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

  .tool--drop-target {
    border-color: #e0596b;
    color: #ff6e82;
    cursor: copy;
  }

  .tool--drop-hover {
    background: #e0596b;
    border-color: #ff3850;
    color: #ffffff;
    transform: scale(1.18);
    box-shadow: 0 0 18px rgba(224, 89, 107, 0.6);
  }

  .tool:focus-visible,
  .flag:focus-visible,
  .stop-btn:focus-visible {
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

  .stop-btn {
    display: grid;
    place-items: center;
    width: 46px;
    height: 46px;
    border: 1px solid #c43e4c;
    border-radius: 14px;
    background: linear-gradient(180deg, #e2636f, #c43e4c);
    color: #fff1f2;
    cursor: pointer;
    box-shadow:
      inset 0 1px 0 rgb(255 255 255 / 30%),
      0 8px 20px rgb(196 62 76 / 35%);
    transition:
      transform 0.13s ease,
      filter 0.15s ease,
      opacity 0.15s ease;
  }

  .stop-btn:hover:not(:disabled) {
    transform: translateY(-1px);
    filter: brightness(1.08);
  }

  .stop-btn:active:not(:disabled) {
    transform: translateY(0);
  }

  .stop-btn:disabled {
    opacity: 0.35;
    cursor: not-allowed;
    box-shadow: none;
  }

  .stop-btn--active {
    box-shadow:
      inset 0 1px 0 rgb(255 255 255 / 40%),
      0 0 16px rgb(226 99 111 / 55%);
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
    min-width: 0;
    overflow-x: hidden;
    margin-top: 4px;
  }

  .dropzone {
    cursor: pointer;
    user-select: none;
    display: inline-flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 8px;
    flex: none;
    width: 124px;
    min-height: 140px;
    padding: 10px 8px;
    box-sizing: border-box;
    border: 1.5px dashed #3c4353;
    border-radius: 16px;
    background: rgb(255 255 255 / 1.5%);
    color: #7f8899;
    align-self: flex-start;
    transition:
      border-color 0.15s ease,
      background 0.15s ease,
      color 0.15s ease;
  }

  .dropzone:hover {
    border-color: #5d677d;
    background: rgb(255 255 255 / 3.5%);
    color: #a4afc3;
  }

  .dropzone:focus-visible {
    outline: 2px solid #7fa8dd;
    outline-offset: 2px;
  }

  .dropzone--over {
    border-color: #7fa8dd;
    background: rgb(127 168 221 / 10%);
    color: #cfe3f8;
  }

  .dropzone--delete {
    border-color: #e0596b;
    border-style: dashed;
    background: rgba(224, 89, 107, 0.12);
    color: #ff9da8;
    cursor: copy;
  }

  .dropzone--delete .dropzone__icon {
    color: #ff5e73;
  }

  .dropzone--delete-over {
    border-color: #ff334e;
    border-width: 2px;
    background: rgba(224, 89, 107, 0.35);
    color: #ffffff;
    box-shadow:
      0 0 20px rgba(224, 89, 107, 0.5),
      inset 0 0 10px rgba(224, 89, 107, 0.25);
  }

  .dropzone--delete-over .dropzone__icon {
    color: #ffffff;
    animation: trash-shake 0.4s ease infinite alternate;
  }

  @keyframes trash-shake {
    from {
      transform: translateY(0) scale(1);
    }
    to {
      transform: translateY(-2px) scale(1.15);
    }
  }

  .dropzone__icon {
    display: grid;
    place-items: center;
    color: #8faed9;
    flex: none;
    transition: transform 0.15s ease, color 0.15s ease;
  }

  .dropzone__text {
    margin: 0;
    font-size: 11px;
    font-weight: 600;
    line-height: 1.25;
    text-align: center;
    letter-spacing: -0.01em;
  }

  .strip {
    display: flex;
    align-items: flex-start;
    gap: 0;
    flex: 1;
    min-width: 0;
    min-height: 176px;
    box-sizing: border-box;
    padding: 6px 24px 26px 14px;
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
    position: relative;
    width: 124px;
    height: 144px;
    cursor: grab;
    transition: transform 0.12s ease;
  }

  .card:hover {
    z-index: 50 !important;
  }

  .card:active {
    cursor: grabbing;
  }

  .card--dragging {
    opacity: 0.45;
    z-index: 60 !important;
  }

  .caret {
    flex: none;
    width: 4px;
    height: 124px;
    margin: 0 2px;
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
      max-width: 180px;
    }

    .dropzone__text {
      font-size: 11.5px;
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

  /* Grands écrans de PC fixe (au-delà de 20 pouces, >= 1700px pour ne pas impacter les portables 15" à 1536px) */
  @media (min-width: 1700px) {
    .program__title {
      font-size: 21px;
    }

    .tool {
      width: 42px;
      height: 42px;
    }

    .flag,
    .stop-btn {
      width: 50px;
      height: 50px;
    }

    .dropzone {
      width: 146px;
      min-height: 162px;
      border-radius: 18px;
    }

    .dropzone__text {
      font-size: 12px;
    }

    .card {
      width: 146px;
      height: 170px;
    }

    .strip {
      min-height: 204px;
      padding: 6px 28px 30px 14px;
    }

    .caret {
      height: 146px;
    }
  }

  /* Très grands écrans (27 pouces et plus / QHD / 4K, >= 2200px) */
  @media (min-width: 2200px) {
    .program__title {
      font-size: 23px;
    }

    .tool {
      width: 46px;
      height: 46px;
    }

    .flag,
    .stop-btn {
      width: 54px;
      height: 54px;
    }

    .dropzone {
      width: 158px;
      min-height: 176px;
      border-radius: 20px;
    }

    .dropzone__text {
      font-size: 13px;
    }

    .card {
      width: 158px;
      height: 184px;
    }

    .strip {
      min-height: 220px;
      padding: 6px 32px 34px 16px;
    }

    .caret {
      height: 158px;
    }
  }

  @media (prefers-reduced-motion: reduce) {
    .flag--busy,
    .caret {
      animation: none;
    }
  }
</style>
