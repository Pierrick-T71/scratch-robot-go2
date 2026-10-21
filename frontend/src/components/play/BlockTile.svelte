<script lang="ts">
  /**
   * Un bloc pastel, avec sa forme « pièce de puzzle ».
   *
   * Le même composant sert dans la bibliothèque (modèle, non modifiable) et
   * dans la timeline (bloc du programme, éventuellement réglable et
   * supprimable). La forme et les couleurs viennent d'ici, jamais du parent :
   * un bloc doit rester reconnaissable partout.
   */
  import Icon from './Icon.svelte';
  import {
    DEGREES,
    DURATIONS,
    specOf,
    type PlayBlockKind,
  } from '../../lib/play/blocks';

  interface Props {
    kind: PlayBlockKind;
    /** Durée affichée pour les blocs de déplacement. */
    seconds?: number;
    /** Angle affiché pour les blocs de rotation. */
    degrees?: number;
    /** Affiche la liste déroulante (timeline seulement). */
    editable?: boolean;
    /** Affiche la croix de suppression. */
    removable?: boolean;
    /** Bloc en cours d'exécution : il s'illumine. */
    running?: boolean;
    onRemove?: () => void;
    onSecondsChange?: (value: number) => void;
    onDegreesChange?: (value: number) => void;
  }

  let {
    kind,
    seconds = 2,
    degrees = 90,
    editable = false,
    removable = false,
    running = false,
    onRemove,
    onSecondsChange,
    onDegreesChange,
  }: Props = $props();

  const spec = $derived(specOf(kind));
  const canEdit = $derived(editable && spec.editable !== undefined);

  function handleChange(event: Event): void {
    const target = event.currentTarget as HTMLSelectElement;
    const value = Number(target.value);
    if (!Number.isFinite(value)) return;
    if (spec.editable === 'degrees') onDegreesChange?.(value);
    else onSecondsChange?.(value);
  }
</script>

<!-- Le glisser-déposer est porté par le parent : ce composant ne décide pas
     s'il est déplaçable, il se contente d'être reconnaissable. -->
<span
  class="blk blk--{spec.tone}"
  class:blk--running={running}
  aria-label={`${spec.hint}${canEdit ? `, ${spec.editable === 'degrees' ? `${degrees} degrés` : `${seconds} secondes`}` : ''}`}
>
  <span class="blk__tab" aria-hidden="true"></span>

  <span class="blk__icon" aria-hidden="true">
    <Icon name={spec.icon} size={22} />
  </span>

  <span class="blk__label">{spec.label}</span>

  {#if canEdit}
    <span class="blk__pill blk__pill--edit">
      <select
        class="blk__select"
        draggable="false"
        aria-label={spec.editable === 'degrees'
          ? 'Angle de rotation, en degrés'
          : 'Durée du déplacement, en secondes'}
        value={String(spec.editable === 'degrees' ? degrees : seconds)}
        onchange={handleChange}
      >
        {#if spec.editable === 'degrees'}
          {#each DEGREES as angle}
            <option value={String(angle)}>{angle}°</option>
          {/each}
        {:else}
          {#each DURATIONS as duration}
            <option value={String(duration)}>{duration} s</option>
          {/each}
        {/if}
      </select>
      <span class="blk__chevron" aria-hidden="true">▾</span>
    </span>
  {:else if spec.editable === 'seconds'}
    <span class="blk__pill">{seconds} s</span>
  {:else if spec.editable === 'degrees'}
    <span class="blk__pill">{degrees}°</span>
  {/if}

  {#if removable}
    <button
      type="button"
      class="blk__remove"
      aria-label="Retirer ce bloc"
      title="Retirer ce bloc"
      onclick={(event) => {
        event.stopPropagation();
        onRemove?.();
      }}
    >
      ×
    </button>
  {/if}
</span>

<style>
  .blk {
    --tone: #a9c9ee;
    --tone-hi: #c8ddf7;
    --tone-ink: #12304f;
    --tone-icon: #1f5f9e;

    position: relative;
    display: flex;
    align-items: center;
    gap: 10px;
    min-height: 62px;
    padding: 10px 16px 10px 12px;
    border-radius: 15px;
    background: linear-gradient(180deg, var(--tone-hi) 0%, var(--tone) 100%);
    color: var(--tone-ink);
    font-size: 17px;
    font-weight: 750;
    letter-spacing: -0.01em;
    line-height: 1.15;
    box-shadow:
      inset 0 1px 0 rgb(255 255 255 / 55%),
      inset 0 -1px 0 rgb(0 0 0 / 8%),
      0 6px 14px rgb(0 0 0 / 22%);
    cursor: inherit;
    user-select: none;
    -webkit-user-select: none;
    transition:
      transform 0.13s ease,
      box-shadow 0.16s ease,
      filter 0.16s ease;
  }

  /* Le tenon : c'est lui qui donne l'air « emboîtable ». */
  .blk__tab {
    position: absolute;
    left: 26px;
    top: -8px;
    width: 30px;
    height: 10px;
    border-radius: 6px 6px 0 0;
    background: var(--tone-hi);
    box-shadow: inset 0 1px 0 rgb(255 255 255 / 55%);
  }

  .blk:hover {
    transform: translateY(-1px);
    box-shadow:
      inset 0 1px 0 rgb(255 255 255 / 55%),
      0 10px 20px rgb(0 0 0 / 28%);
  }

  .blk--blue {
    --tone: #a9c9ee;
    --tone-hi: #c8ddf7;
    --tone-ink: #12304f;
    --tone-icon: #1f5f9e;
  }

  .blk--violet {
    --tone: #c3a4f2;
    --tone-hi: #d9c6fb;
    --tone-ink: #2f1c4d;
    --tone-icon: #6b46b8;
  }

  .blk--peach {
    --tone: #f5c3a6;
    --tone-hi: #fbd6bf;
    --tone-ink: #4a2414;
    --tone-icon: #c96b4a;
  }

  .blk--mint {
    --tone: #b4e6c4;
    --tone-hi: #cdf2d8;
    --tone-ink: #143d26;
    --tone-icon: #2f8f5b;
  }

  .blk--rose {
    --tone: #f6b8cd;
    --tone-hi: #fbd3e0;
    --tone-ink: #4a1430;
    --tone-icon: #c94b7c;
  }

  .blk--sky {
    --tone: #c3d6ea;
    --tone-hi: #dbe8f5;
    --tone-ink: #1d2b3c;
    --tone-icon: #4a6b91;
  }

  .blk--sun {
    --tone: #f7d79c;
    --tone-hi: #fce7bb;
    --tone-ink: #4a3410;
    --tone-icon: #c78d1c;
  }

  .blk__icon {
    display: grid;
    place-items: center;
    flex: none;
    width: 40px;
    height: 40px;
    border-radius: 12px;
    background: var(--tone-icon);
    color: #fff;
    box-shadow: inset 0 1px 0 rgb(255 255 255 / 22%);
  }

  .blk__label {
    min-width: 0;
    text-wrap: balance;
  }

  .blk__pill {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    margin-left: auto;
    min-height: 34px;
    padding: 4px 13px;
    border-radius: var(--radius-pill, 999px);
    background: #fff;
    color: #1b2330;
    font-size: 16px;
    font-weight: 800;
    white-space: nowrap;
    box-shadow:
      inset 0 -1px 0 rgb(0 0 0 / 10%),
      0 1px 2px rgb(0 0 0 / 18%);
  }

  .blk__pill--edit {
    position: relative;
    padding: 0 8px 0 12px;
  }

  .blk__select {
    appearance: none;
    border: 0;
    background: transparent;
    padding: 6px 16px 6px 0;
    font: inherit;
    font-size: 16px;
    font-weight: 800;
    color: inherit;
    cursor: pointer;
  }

  .blk__select:focus-visible {
    outline: 2px solid #1f5f9e;
    outline-offset: 2px;
    border-radius: 8px;
  }

  .blk__chevron {
    position: absolute;
    right: 8px;
    top: 50%;
    transform: translateY(-55%);
    font-size: 11px;
    color: #5a6478;
    pointer-events: none;
  }

  .blk__remove {
    position: absolute;
    top: -9px;
    right: -9px;
    width: 26px;
    height: 26px;
    display: grid;
    place-items: center;
    padding: 0 0 2px;
    border-radius: 50%;
    border: 1px solid #4a5265;
    background: #2b303c;
    color: #d8deea;
    font-size: 17px;
    font-weight: 700;
    line-height: 1;
    cursor: pointer;
    box-shadow: 0 3px 8px rgb(0 0 0 / 35%);
    transition:
      background 0.14s ease,
      color 0.14s ease,
      transform 0.12s ease;
  }

  .blk__remove:hover {
    background: #e0596b;
    border-color: #e0596b;
    color: #fff;
    transform: scale(1.08);
  }

  .blk__remove:focus-visible {
    outline: 2px solid #fff;
    outline-offset: 2px;
  }

  .blk--running {
    animation: breathe 1.4s ease-in-out infinite;
  }

  .blk--running::after {
    content: '';
    position: absolute;
    inset: -4px;
    border-radius: 18px;
    border: 3px solid rgb(255 255 255 / 85%);
    box-shadow: 0 0 22px rgb(255 255 255 / 35%);
    pointer-events: none;
  }

  @keyframes breathe {
    0%,
    100% {
      transform: translateY(-1px) scale(1);
    }
    50% {
      transform: translateY(-1px) scale(1.015);
    }
  }

  @media (prefers-reduced-motion: reduce) {
    .blk,
    .blk__remove {
      transition: none;
    }
    .blk--running {
      animation: none;
    }
  }
</style>
