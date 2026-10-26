<script lang="ts">
  /**
   * Écran plein écran du mode veille prolongée (« En veille »).
   *
   * Bloque toute interaction avec l'application pendant la veille et ses
   * transitions (mise en veille et réveil progressifs).
   * Fournit un bouton de réveil et informe l'utilisateur sur l'état du robot
   * et l'optimisation de la batterie.
   */
  import Icon from './Icon.svelte';
  import type { RobotStatus } from '../../lib/api/client';

  interface Props {
    status: RobotStatus;
    onWake: () => void;
  }

  let { status, onWake }: Props = $props();

  const isTransitioning = $derived(status.standbyTransition !== null);
  const isEntering = $derived(status.standbyTransition === 'entering');
  const isWaking = $derived(status.standbyTransition === 'waking');

  const title = $derived(
    isEntering
      ? 'Mise en veille…'
      : isWaking
        ? 'Réveil en cours…'
        : 'En veille',
  );

  const description = $derived(
    isEntering
      ? 'Le robot s’allonge doucement et coupe son LiDAR pour économiser la batterie.'
      : isWaking
        ? 'Rallumage du LiDAR et des moteurs, le robot se remet debout…'
        : 'Le robot est allongé au repos. Le LiDAR et les moteurs sont coupés pour maximiser l’autonomie de la batterie.',
  );
</script>

<div
  class="standby-screen"
  role="dialog"
  aria-modal="true"
  aria-label="Écran de veille du robot"
>
  <div class="standby-card">
    <div class="standby-visual" class:standby-visual--pulse={isTransitioning}>
      <div class="standby-halo"></div>
      <div class="standby-icon-wrap">
        {#if isTransitioning}
          <div class="standby-spinner" aria-hidden="true">
            <Icon name="refresh" size={48} />
          </div>
        {:else}
          <div class="standby-moon" aria-hidden="true">
            <Icon name="moon" size={54} />
          </div>
        {/if}
      </div>
    </div>

    <h1 class="standby-title">{title}</h1>
    <p class="standby-description">{description}</p>

    {#if status.batteryPercent !== null}
      <div class="standby-badge">
        <Icon name="battery" size={18} />
        <span>Batterie : {Math.round(status.batteryPercent)}%</span>
      </div>
    {/if}

    <div class="standby-notice">
      <span class="standby-notice__icon" aria-hidden="true">ℹ️</span>
      <p class="standby-notice__text">
        <strong>Économie d’énergie :</strong> Le LiDAR et les moteurs sont coupés.
        La carte informatique reste alimentée pour permettre ce réveil à distance.
      </p>
    </div>

    <div class="standby-actions">
      <button
        type="button"
        class="standby-wake-btn"
        disabled={isTransitioning}
        onclick={onWake}
      >
        {#if isWaking}
          <span class="standby-btn-spinner" aria-hidden="true">
            <Icon name="refresh" size={22} />
          </span>
          <span>Réveil en cours…</span>
        {:else if isEntering}
          <span class="standby-btn-spinner" aria-hidden="true">
            <Icon name="refresh" size={22} />
          </span>
          <span>Mise en veille…</span>
        {:else}
          <Icon name="sun" size={24} />
          <span>Réveiller le robot</span>
        {/if}
      </button>
    </div>
  </div>
</div>

<style>
  .standby-screen {
    position: fixed;
    inset: 0;
    z-index: 300;
    display: grid;
    place-items: center;
    padding: 24px;
    background: radial-gradient(
      circle at center 40%,
      rgb(17 24 39 / 94%) 0%,
      rgb(8 11 18 / 98%) 100%
    );
    backdrop-filter: blur(12px);
    animation: standby-fade-in 0.25s ease-out;
    user-select: none;
  }

  @keyframes standby-fade-in {
    from {
      opacity: 0;
      transform: scale(0.98);
    }
    to {
      opacity: 1;
      transform: scale(1);
    }
  }

  .standby-card {
    display: flex;
    flex-direction: column;
    align-items: center;
    max-width: 520px;
    width: 100%;
    padding: 38px 32px 34px;
    border-radius: 28px;
    background: linear-gradient(
      180deg,
      rgb(30 41 59 / 70%) 0%,
      rgb(15 23 42 / 85%) 100%
    );
    border: 1px solid rgb(255 255 255 / 12%);
    box-shadow:
      0 24px 60px rgb(0 0 0 / 60%),
      inset 0 1px 0 rgb(255 255 255 / 10%);
    text-align: center;
  }

  .standby-visual {
    position: relative;
    display: grid;
    place-items: center;
    width: 110px;
    height: 110px;
    margin-bottom: 22px;
  }

  .standby-halo {
    position: absolute;
    inset: 0;
    border-radius: 50%;
    background: radial-gradient(
      circle,
      rgb(99 102 241 / 35%) 0%,
      rgb(99 102 241 / 0%) 70%
    );
    filter: blur(10px);
    animation: halo-breathe 4s infinite ease-in-out;
  }

  @keyframes halo-breathe {
    0%,
    100% {
      transform: scale(1);
      opacity: 0.6;
    }
    50% {
      transform: scale(1.3);
      opacity: 1;
    }
  }

  .standby-icon-wrap {
    position: relative;
    display: grid;
    place-items: center;
    width: 90px;
    height: 90px;
    border-radius: 50%;
    background: linear-gradient(135deg, #1e293b, #0f172a);
    border: 1px solid rgb(129 140 248 / 30%);
    box-shadow: 0 10px 24px rgb(0 0 0 / 40%);
  }

  .standby-moon {
    color: #a5b4fc;
    filter: drop-shadow(0 0 12px rgb(165 180 252 / 60%));
    animation: moon-float 3s infinite ease-in-out;
  }

  @keyframes moon-float {
    0%,
    100% {
      transform: translateY(0);
    }
    50% {
      transform: translateY(-4px);
    }
  }

  .standby-spinner {
    color: #818cf8;
    animation: spin 1.2s infinite linear;
  }

  .standby-btn-spinner {
    display: inline-flex;
    animation: spin 1.2s infinite linear;
  }

  @keyframes spin {
    from {
      transform: rotate(0deg);
    }
    to {
      transform: rotate(360deg);
    }
  }

  .standby-title {
    margin: 0 0 12px;
    font-size: 32px;
    font-weight: 800;
    letter-spacing: -0.02em;
    color: #f8fafc;
  }

  .standby-description {
    margin: 0 0 20px;
    font-size: 16px;
    line-height: 1.5;
    color: #cbd5e1;
  }

  .standby-badge {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 6px 14px;
    margin-bottom: 20px;
    border-radius: 999px;
    background: rgb(255 255 255 / 6%);
    border: 1px solid rgb(255 255 255 / 10%);
    font-size: 14px;
    font-weight: 600;
    color: #94a3b8;
  }

  .standby-notice {
    display: flex;
    align-items: flex-start;
    gap: 12px;
    width: 100%;
    padding: 14px 16px;
    margin-bottom: 26px;
    border-radius: 16px;
    background: rgb(99 102 241 / 10%);
    border: 1px solid rgb(129 140 248 / 25%);
    text-align: left;
  }

  .standby-notice__icon {
    font-size: 18px;
    line-height: 1.2;
    flex: none;
  }

  .standby-notice__text {
    margin: 0;
    font-size: 13.5px;
    line-height: 1.45;
    color: #c7d2fe;
  }

  .standby-notice__text strong {
    color: #e0e7ff;
  }

  .standby-actions {
    width: 100%;
  }

  .standby-wake-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 12px;
    width: 100%;
    min-height: 56px;
    padding: 12px 24px;
    border-radius: 999px;
    border: 1px solid rgb(254 240 138 / 50%);
    background: linear-gradient(135deg, #f59e0b, #d97706);
    color: #1e1b4b;
    font-family: inherit;
    font-size: 19px;
    font-weight: 700;
    cursor: pointer;
    box-shadow:
      0 10px 24px rgb(217 119 6 / 35%),
      inset 0 1px 0 rgb(255 255 255 / 30%);
    transition:
      transform 0.15s ease,
      filter 0.15s ease,
      opacity 0.15s ease;
  }

  .standby-wake-btn:hover:not(:disabled) {
    transform: translateY(-2px);
    filter: brightness(1.1);
    box-shadow:
      0 14px 30px rgb(217 119 6 / 45%),
      inset 0 1px 0 rgb(255 255 255 / 30%);
  }

  .standby-wake-btn:active:not(:disabled) {
    transform: translateY(1px);
  }

  .standby-wake-btn:disabled {
    opacity: 0.6;
    cursor: not-allowed;
    background: #334155;
    border-color: #475569;
    color: #94a3b8;
    box-shadow: none;
  }

  @media (max-width: 600px) {
    .standby-card {
      padding: 28px 20px 24px;
    }

    .standby-title {
      font-size: 26px;
    }

    .standby-wake-btn {
      font-size: 17px;
      min-height: 50px;
    }
  }
</style>
