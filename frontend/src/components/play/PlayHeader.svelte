<script lang="ts">
  /**
   * Barre supérieure : identité, commandes principales, état de la liaison.
   *
   * « Lancer » et « Arrêter » restent distincts et toujours visibles : arrêter
   * un robot ne doit jamais demander de chercher un menu.
   */
  import Icon from './Icon.svelte';
  import type { RobotStatus } from '../../lib/api/client';

  interface Props {
    status: RobotStatus;
    busy: boolean;
    blockCount: number;
    /** Le robot marche-t-il tout seul ? */
    autonome?: boolean;
    onStart: () => void;
    onStop: () => void;
    onSave: () => void;
    onOpenRobot: () => void;
    onToggleAutonome?: () => void;
  }

  let {
    status,
    busy,
    blockCount,
    autonome = false,
    onStart,
    onStop,
    onSave,
    onOpenRobot,
    onToggleAutonome,
  }: Props = $props();

  const label = $derived(
    status.mode === 'simulation'
      ? 'Simulation'
      : status.connected
        ? 'Go2 Connecté'
        : 'Go2 hors ligne',
  );
  const tone = $derived(
    status.mode === 'simulation'
      ? 'sim'
      : status.connected
        ? 'on'
        : 'off',
  );
</script>

<header class="bar">
  <div class="brand">
    <span class="brand__logo" aria-hidden="true">
      <svg viewBox="0 0 64 64" width="46" height="46">
        <ellipse cx="17" cy="21" rx="8.5" ry="12" fill="#3a3f4c" transform="rotate(-14 17 21)" />
        <ellipse cx="47" cy="21" rx="8.5" ry="12" fill="#3a3f4c" transform="rotate(14 47 21)" />
        <circle cx="32" cy="34" r="20" fill="#f4f6fb" />
        <circle cx="32" cy="38" r="15" fill="#e9edf6" />
        <circle cx="24.5" cy="32" r="7.2" fill="none" stroke="#2b3140" stroke-width="2.2" />
        <circle cx="39.5" cy="32" r="7.2" fill="none" stroke="#2b3140" stroke-width="2.2" />
        <path d="M31.7 32h0.6" stroke="#2b3140" stroke-width="2.2" stroke-linecap="round" />
        <circle cx="24.5" cy="32" r="2.4" fill="#2b3140" />
        <circle cx="39.5" cy="32" r="2.4" fill="#2b3140" />
        <ellipse cx="32" cy="43" rx="5" ry="3.6" fill="#2b3140" />
        <path d="M32 46.6v3" stroke="#2b3140" stroke-width="2" stroke-linecap="round" />
      </svg>
    </span>
    <h1 class="brand__name">
      Go2&nbsp;Play
      <span class="brand__sparkle" aria-hidden="true">
        <Icon name="sparkle" size={16} />
      </span>
    </h1>
  </div>

  <div class="actions" role="group" aria-label="Commandes du programme">
    <button
      type="button"
      class="action action--run"
      disabled={busy || blockCount === 0}
      onclick={onStart}
      title={blockCount === 0 ? 'Ajoute d’abord un bloc' : 'Lancer le programme'}
    >
      <span class="action__icon action__icon--run">
        <Icon name="play" size={20} />
      </span>
      Lancer
    </button>

    <button
      type="button"
      class="action action--stop"
      disabled={!busy}
      onclick={onStop}
      title="Arrêter le programme en cours"
    >
      <span class="action__icon action__icon--stop">
        <Icon name="stop" size={18} />
      </span>
      Arrêter
    </button>

    <button
      type="button"
      class="action action--save"
      onclick={onSave}
      title="Enregistrer le programme sur cet appareil"
    >
      <span class="action__icon action__icon--save">
        <Icon name="save" size={19} />
      </span>
      Sauvegarder
    </button>
  </div>

  <button
    type="button"
    class="status status--{tone}"
    onclick={onOpenRobot}
    title="Brancher ou régler le robot"
  >
    <span class="status__dot" aria-hidden="true"></span>
    {label}
  </button>

  <button
    type="button"
    class="stars"
    class:stars--on={autonome}
    aria-pressed={autonome}
    aria-label={autonome
      ? 'Arrêter la marche autonome'
      : 'Faire marcher le robot tout seul'}
    title={autonome
      ? 'Arrêter la marche autonome'
      : 'Le robot se débrouille seul'}
    onclick={onToggleAutonome}
  >
    <Icon name="sparkle" size={20} />
    <span class="stars__label">Autonome</span>
  </button>
</header>

<style>
  .bar {
    display: flex;
    align-items: center;
    gap: 18px;
    padding: 4px 6px 14px;
    flex-wrap: wrap;
  }

  .brand {
    display: flex;
    align-items: center;
    gap: 12px;
    min-width: 0;
  }

  .brand__logo {
    display: grid;
    place-items: center;
    width: 58px;
    height: 58px;
    border-radius: 18px;
    background: linear-gradient(180deg, #2f3442, #262a35);
    box-shadow:
      inset 0 1px 0 rgb(255 255 255 / 8%),
      0 8px 18px rgb(0 0 0 / 32%);
  }

  .brand__name {
    display: inline-flex;
    align-items: flex-start;
    gap: 6px;
    margin: 0;
    font-size: 29px;
    font-weight: 800;
    letter-spacing: -0.025em;
    color: #f2f5fa;
    white-space: nowrap;
  }

  .brand__sparkle {
    color: #9fb6ea;
    transform: translateY(-2px);
  }

  .actions {
    display: flex;
    align-items: center;
    gap: 12px;
    margin: 0 auto;
    flex-wrap: wrap;
  }

  .action {
    display: inline-flex;
    align-items: center;
    gap: 11px;
    min-height: 56px;
    padding: 6px 22px 6px 8px;
    border-radius: 999px;
    border: 1px solid transparent;
    font-family: inherit;
    font-size: 19px;
    font-weight: 600;
    letter-spacing: -0.01em;
    cursor: pointer;
    transition:
      background 0.16s ease,
      transform 0.12s ease,
      filter 0.16s ease;
  }

  .action:hover:not(:disabled) {
    transform: translateY(-1px);
    filter: brightness(1.08);
  }

  .action:active:not(:disabled) {
    transform: translateY(0);
  }

  .action:disabled {
    opacity: 0.42;
    cursor: not-allowed;
    filter: saturate(0.6);
  }

  .action:focus-visible {
    outline: 2px solid #cfe0f5;
    outline-offset: 3px;
  }

  .action__icon {
    display: grid;
    place-items: center;
    width: 42px;
    height: 42px;
    border-radius: 50%;
    color: #fff;
    flex: none;
  }

  .action--run {
    background: rgb(47 157 92 / 16%);
    border-color: rgb(88 196 128 / 42%);
    color: #9fe3b6;
  }

  .action__icon--run {
    background: linear-gradient(180deg, #49c479, #2f9d5c);
    box-shadow: 0 4px 12px rgb(47 157 92 / 45%);
  }

  .action--stop {
    background: rgb(198 62 74 / 15%);
    border-color: rgb(226 100 110 / 40%);
    color: #f3a7ae;
  }

  .action__icon--stop {
    background: linear-gradient(180deg, #e2636f, #c43e4c);
    box-shadow: 0 4px 12px rgb(196 62 76 / 42%);
  }

  .action--save {
    background: rgb(70 112 196 / 16%);
    border-color: rgb(112 150 224 / 40%);
    color: #a9c2ef;
  }

  .action__icon--save {
    background: linear-gradient(180deg, #5b86d6, #3f68b8);
    box-shadow: 0 4px 12px rgb(63 104 184 / 42%);
  }

  .status {
    display: inline-flex;
    align-items: center;
    gap: 10px;
    min-height: 52px;
    padding: 0 22px;
    border-radius: 999px;
    font-family: inherit;
    font-size: 18px;
    font-weight: 600;
    letter-spacing: -0.01em;
    cursor: pointer;
    transition:
      filter 0.15s ease,
      transform 0.12s ease;
    white-space: nowrap;
  }

  .status:hover {
    filter: brightness(1.1);
    transform: translateY(-1px);
  }

  .status:focus-visible {
    outline: 2px solid #cfe0f5;
    outline-offset: 3px;
  }

  .status--on {
    background: rgb(47 157 92 / 14%);
    border: 1px solid rgb(88 196 128 / 38%);
    color: #a6e6bb;
  }

  .status--off {
    background: rgb(198 62 74 / 14%);
    border: 1px solid rgb(226 100 110 / 38%);
    color: #f0aab1;
  }

  .status--sim {
    background: rgb(196 150 60 / 14%);
    border: 1px solid rgb(224 180 90 / 34%);
    color: #ecc98a;
  }

  .status__dot {
    width: 13px;
    height: 13px;
    border-radius: 50%;
    background: currentColor;
    box-shadow: 0 0 12px currentColor;
  }

  /* Le mode autonome : un petit bouton a part, avec des etoiles. */
  .stars {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    min-height: 48px;
    padding: 0 18px;
    border-radius: 999px;
    border: 1px solid rgb(160 130 220 / 38%);
    background: rgb(140 110 210 / 16%);
    color: #cdbcf2;
    font-family: inherit;
    font-size: 15px;
    font-weight: 650;
    cursor: pointer;
    white-space: nowrap;
    transition:
      background 0.15s ease,
      color 0.15s ease,
      transform 0.12s ease;
  }

  .stars:hover {
    background: rgb(150 120 220 / 26%);
    color: #e3d7fb;
    transform: translateY(-1px);
  }

  .stars:focus-visible {
    outline: 2px solid #cfe0f5;
    outline-offset: 3px;
  }

  .stars--on {
    background: linear-gradient(180deg, #b18cf0, #8a63d8);
    border-color: rgb(220 200 255 / 60%);
    color: #1a1030;
    box-shadow:
      inset 0 1px 0 rgb(255 255 255 / 30%),
      0 6px 18px rgb(138 99 216 / 40%);
  }

  @media (max-width: 720px) {
    .stars__label {
      display: none;
    }

    .stars {
      padding: 0 14px;
    }
  }

  @media (max-width: 1180px) {
    .actions {
      order: 3;
      width: 100%;
      margin: 0;
    }

    .status {
      margin-left: auto;
    }
  }

  @media (max-width: 720px) {
    .brand__name {
      font-size: 24px;
    }

    .brand__logo {
      width: 50px;
      height: 50px;
    }

    .action {
      min-height: 48px;
      font-size: 16px;
      padding-right: 16px;
    }

    .action__icon {
      width: 36px;
      height: 36px;
    }

    .status {
      min-height: 44px;
      font-size: 15px;
      padding: 0 16px;
    }
  }
</style>
