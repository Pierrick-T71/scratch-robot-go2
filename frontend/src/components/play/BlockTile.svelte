<script lang="ts">
  /**
   * Un bloc pastel en forme de pièce de puzzle carrée.
   *
   * Forme de puzzle carrée avec languettes arrondies (mâles) et creux (femelles)
   * sur tous les côtés pour un emboîtement fluide dans toutes les directions,
   * sans connecteur parasite ni croix.
   *
   * Organisation interne :
   *  - Icône du mouvement/action en haut et bien centrée
   *  - Texte descriptif en bas et bien centré
   *  - L'ensemble parfaitement disposé au milieu de la pièce de puzzle
   */
  import Icon from './Icon.svelte';
  import {
    DEGREES,
    DURATIONS,
    specOfOrFallback,
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
    /** Bloc en cours d'exécution : il s'illumine. */
    running?: boolean;
    /** Forme puzzle (conservé pour rétrocompatibilité). */
    puzzle?: boolean;
    /** Premier bloc (conservé pour rétrocompatibilité). */
    isFirst?: boolean;
    /** Dernier bloc (conservé pour rétrocompatibilité). */
    isLast?: boolean;
    /** Conservé pour compatibilité de signature. */
    removable?: boolean;
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
    puzzle = true,
    isFirst = false,
    isLast = false,
    onRemove,
    onSecondsChange,
    onDegreesChange,
  }: Props = $props();

  const spec = $derived(specOfOrFallback(kind));
  const canEdit = $derived(editable && spec.editable !== undefined);

  /**
   * Contour géométrique de la pièce de puzzle carrée (100x100 de base, s'étendant à 115x115 avec tenons) :
   * - Haut : creux femelle arrondi (y=0 à y=15)
   * - Droite : languette mâle arrondie en relief (x=100 à x=115)
   * - Bas : languette mâle arrondie en relief (y=100 à y=115)
   * - Gauche : creux femelle arrondi (x=0 à x=15)
   * - Coins arrondis (rayon 8)
   */
  const PUZZLE_PATH =
    'M 8 0 H 38 C 40 0, 40 3, 38 5 C 35 8, 35 15, 50 15 C 65 15, 65 8, 62 5 C 60 3, 60 0, 62 0 H 92 Q 100 0 100 8 V 38 C 100 40, 103 40, 105 38 C 108 35, 115 35, 115 50 C 115 65, 108 65, 105 62 C 103 60, 100 60, 100 62 V 92 Q 100 100 92 100 H 62 C 60 100, 60 103, 62 105 C 65 108, 65 115, 50 115 C 35 115, 35 108, 38 105 C 40 103, 40 100, 38 100 H 8 Q 0 100 0 92 V 62 C 0 60, 3 60, 5 62 C 8 65, 15 65, 15 50 C 15 35, 8 35, 5 38 C 3 40, 0 40, 0 38 V 8 Q 0 0 8 0 Z';

  const TONE_GRADIENTS: Record<string, { hi: string; lo: string }> = {
    blue: { hi: '#c8ddf7', lo: '#a9c9ee' },
    violet: { hi: '#d9c6fb', lo: '#c3a4f2' },
    peach: { hi: '#fbd6bf', lo: '#f5c3a6' },
    mint: { hi: '#cdf2d8', lo: '#b4e6c4' },
    rose: { hi: '#fbd3e0', lo: '#f6b8cd' },
    sky: { hi: '#dbe8f5', lo: '#c3d6ea' },
    sun: { hi: '#fce7bb', lo: '#f7d79c' },
  };

  const gradient = $derived(
    TONE_GRADIENTS[spec.tone] ?? { hi: '#c8ddf7', lo: '#a9c9ee' },
  );

  function handleChange(event: Event): void {
    const target = event.currentTarget as HTMLSelectElement;
    const value = Number(target.value);
    if (!Number.isFinite(value)) return;
    if (spec.editable === 'degrees') onDegreesChange?.(value);
    else onSecondsChange?.(value);
  }
</script>

<span
  class="blk blk--{spec.tone}"
  class:blk--running={running}
  aria-label={`${spec.hint}${canEdit ? `, ${spec.editable === 'degrees' ? `${degrees} degrés` : `${seconds} secondes`}` : ''}`}
>
  <svg class="blk__svg" viewBox="0 0 115 115" aria-hidden="true">
    <defs>
      <linearGradient id="blk-grad-{spec.tone}" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color={gradient.hi} />
        <stop offset="100%" stop-color={gradient.lo} />
      </linearGradient>
    </defs>
    <path
      class="blk__path"
      d={PUZZLE_PATH}
      fill="url(#blk-grad-{spec.tone})"
      stroke="rgba(255, 255, 255, 0.72)"
      stroke-width="1.2"
    />
  </svg>

  <span class="blk__content">
    <span class="blk__icon" aria-hidden="true">
      <Icon name={spec.icon} size={22} />
    </span>

    <span class="blk__bottom">
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
          <span class="blk__pill-val">{spec.editable === 'degrees' ? `${degrees}°` : `${seconds} s`}</span>
          <span class="blk__chevron-badge" aria-hidden="true">
            <svg width="8" height="6" viewBox="0 0 8 6" fill="none">
              <path d="M1 1.5L4 4.5L7 1.5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
          </span>
        </span>
      {:else if spec.editable === 'seconds'}
        <span class="blk__pill">{seconds} s</span>
      {:else if spec.editable === 'degrees'}
        <span class="blk__pill">{degrees}°</span>
      {/if}
    </span>
  </span>
</span>

<style>
  .blk {
    --tone: #a9c9ee;
    --tone-hi: #c8ddf7;
    --tone-ink: #12304f;
    --tone-icon: #1f5f9e;

    position: relative;
    display: inline-flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    width: 124px;
    height: 124px;
    cursor: inherit;
    user-select: none;
    -webkit-user-select: none;
    transition:
      transform 0.13s ease,
      filter 0.16s ease;
  }

  .blk__svg {
    position: absolute;
    left: 0;
    top: 0;
    width: 142.6px;
    height: 142.6px;
    pointer-events: none;
    overflow: visible;
    filter: drop-shadow(0 4px 8px rgb(0 0 0 / 22%));
    transition: filter 0.16s ease;
  }

  .blk:hover {
    transform: translateY(-2px);
  }

  .blk:hover .blk__svg {
    filter: drop-shadow(0 8px 16px rgb(0 0 0 / 30%));
  }

  .blk__content {
    position: relative;
    z-index: 2;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    width: 124px;
    height: 124px;
    padding: 16px 4px 7px 16px;
    box-sizing: border-box;
    text-align: center;
    pointer-events: auto;
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
    width: 36px;
    height: 36px;
    border-radius: 11px;
    background: var(--tone-icon);
    color: #fff;
    box-shadow: inset 0 1px 0 rgb(255 255 255 / 35%);
    margin-bottom: 3px;
  }

  .blk__bottom {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    min-width: 0;
    width: 100%;
  }

  .blk__label {
    min-width: 0;
    max-width: 96px;
    font-size: 13.5px;
    font-weight: 800;
    letter-spacing: -0.015em;
    line-height: 1.15;
    color: var(--tone-ink);
    text-align: center;
    text-wrap: balance;
    word-break: normal;
  }

  .blk__pill {
    position: relative;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
    margin-top: 4px;
    min-height: 25px;
    padding: 2px 10px;
    border-radius: 999px;
    background: #ffffff;
    color: #111827;
    font-size: 13px;
    font-weight: 850;
    line-height: 1;
    white-space: nowrap;
    border: 1.5px solid rgba(255, 255, 255, 0.95);
    box-shadow:
      0 2px 6px rgba(0, 0, 0, 0.14),
      0 1px 2px rgba(0, 0, 0, 0.08);
    flex: none;
    transition: transform 0.12s ease, box-shadow 0.12s ease;
  }

  .blk__pill--edit {
    padding: 1px 6px 1px 11px;
    cursor: pointer;
  }

  .blk__pill--edit:hover {
    box-shadow: 0 4px 10px rgba(0, 0, 0, 0.22);
    transform: translateY(-0.5px);
  }

  .blk__select {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    opacity: 0;
    cursor: pointer;
    z-index: 3;
    font-size: 16px;
  }

  .blk__pill--edit:focus-within {
    box-shadow: 0 0 0 2px #1f5f9e, 0 3px 8px rgba(0, 0, 0, 0.2);
  }

  .blk__pill-val {
    position: relative;
    z-index: 1;
    font: inherit;
    font-size: 13px;
    font-weight: 850;
    color: #111827;
  }

  .blk__chevron-badge {
    position: relative;
    z-index: 1;
    width: 16px;
    height: 16px;
    border-radius: 999px;
    background: #e2e8f0;
    display: flex;
    align-items: center;
    justify-content: center;
    color: #475569;
    flex: none;
    transition: background 0.12s ease, color 0.12s ease;
  }

  .blk__pill--edit:hover .blk__chevron-badge {
    background: #cbd5e1;
    color: #0f172a;
  }

  .blk--running {
    animation: breathe 1.4s ease-in-out infinite;
  }

  .blk--running .blk__svg {
    filter: drop-shadow(0 0 10px rgb(255 255 255 / 85%)) drop-shadow(0 6px 14px rgb(0 0 0 / 30%));
  }

  .blk--running .blk__path {
    stroke: #ffffff;
    stroke-width: 2px;
  }

  @keyframes breathe {
    0%,
    100% {
      transform: translateY(-2px) scale(1);
    }
    50% {
      transform: translateY(-2px) scale(1.03);
    }
  }

  @media (prefers-reduced-motion: reduce) {
    .blk {
      transition: none;
    }
    .blk--running {
      animation: none;
    }
  }
</style>
