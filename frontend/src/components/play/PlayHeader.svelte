<script lang="ts">
  /**
   * Barre supérieure : identité, pilotage manuel, arrêt et état de la liaison.
   *
   * Le programme se lance avec le drapeau de « Mon Programme ». Ici, le gros
   * bouton ouvre le mode manuel : ZQSD pour déplacer le robot, relâcher une
   * touche pour l'arrêter.
   */
  import Icon from './Icon.svelte';
  import type { RobotStatus } from '../../lib/api/client';

  interface Props {
    status: RobotStatus;
    busy: boolean;
    onManual: () => void;
    onStop: () => void;
    onSave: () => void;
    onOpenRobot: () => void;
    /** Active/coupe la sécurité lidar du service. */
    onToggleSafety: (enabled: boolean) => void;
    /** Active/coupe la veille prolongée du robot. */
    onToggleStandby: (enabled: boolean) => void;
  }

  let {
    status,
    busy,
    onManual,
    onStop,
    onSave,
    onOpenRobot,
    onToggleSafety,
    onToggleStandby,
  }: Props = $props();

  const label = $derived(
    status.safetyReason
      ? 'Robot à l’arrêt'
      : status.mode === 'simulation'
        ? 'Simulation'
        : status.connected
          ? 'Go2 Connecté'
          : 'Go2 hors ligne',
  );
  const tone = $derived(
    status.safetyReason
      ? 'off'
      : status.mode === 'simulation'
        ? 'sim'
        : status.connected
          ? 'on'
          : 'off',
  );

  const safetyAvailable = $derived(Boolean(status.obstacleSafetyAvailable));
  const safetyOn = $derived(status.obstacleSafetyEnabled !== false);
  const safetyState = $derived(
    !safetyAvailable
      ? 'indisponible'
      : safetyOn
        ? 'activée'
        : 'désactivée',
  );
  const standbyOn = $derived(Boolean(status.standby));
  const standbyState = $derived(
    status.standbyTransition === 'entering'
      ? 'mise en veille…'
      : status.standbyTransition === 'waking'
        ? 'réveil en cours…'
        : standbyOn
          ? 'activée'
          : 'éteinte',
  );
  const standbyTitle = $derived(
    status.standbyTransition !== null
      ? 'Transition de veille en cours…'
      : standbyOn
        ? 'Réveiller le robot (relever et rallumer les capteurs)'
        : 'Passer en veille économique (allonger et couper le LiDAR)',
  );

  const safetyTitle = $derived(
    !safetyAvailable
      ? 'La sécurité lidar est disponible quand le robot réel est connecté'
      : busy
        ? 'Attends la fin du programme ou du mode manuel pour changer la sécurité'
        : safetyOn
          ? 'Couper la vérification de place du service (l’anti-obstacle du robot reste actif)'
          : 'Réactiver la vérification de place du service',
  );

  const manualDisabled = $derived(
    busy ||
      Boolean(status.safetyReason) ||
      (status.mode === 'real' && !status.connected),
  );
  const manualTitle = $derived(
    busy
      ? 'Attends la fin du programme en cours'
      : status.safetyReason
        ? 'Repose le robot au sol et attends qu’il soit stable'
        : status.mode === 'real' && !status.connected
          ? 'Branche le robot réel pour piloter à la main'
          : 'Déplacer le robot avec les touches ZQSD',
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
      class="action action--manual"
      disabled={manualDisabled}
      onclick={onManual}
      title={manualTitle}
    >
      <span class="action__icon action__icon--manual">
        <Icon name="gamepad" size={21} />
      </span>
      Mode manuel
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

  <div class="topright">
    <button
      type="button"
      class="safety-switch standby-switch"
      class:standby-switch--on={standbyOn}
      class:standby-switch--transition={status.standbyTransition !== null}
      role="switch"
      aria-checked={standbyOn}
      aria-label="Mode veille"
      disabled={status.standbyTransition !== null}
      title={standbyTitle}
      onclick={() => onToggleStandby(!standbyOn)}
    >
      <span class="safety-switch__copy">
        <span class="safety-switch__label">Veille</span>
        <span class="safety-switch__state">{standbyState}</span>
      </span>
      <span class="safety-switch__track" aria-hidden="true">
        <span class="safety-switch__thumb"></span>
      </span>
    </button>

    <button
      type="button"
      class="safety-switch"
      class:safety-switch--off={safetyAvailable && !safetyOn}
      class:safety-switch--unavailable={!safetyAvailable}
      role="switch"
      aria-checked={safetyOn}
      aria-label="Sécurité lidar"
      disabled={busy || !safetyAvailable}
      title={safetyTitle}
      onclick={() => onToggleSafety(!safetyOn)}
    >
      <span class="safety-switch__copy">
        <span class="safety-switch__label">Sécurité</span>
        <span class="safety-switch__state">{safetyState}</span>
      </span>
      <span class="safety-switch__track" aria-hidden="true">
        <span class="safety-switch__thumb"></span>
      </span>
    </button>

    <button
      type="button"
      class="status status--{tone}"
      onclick={onOpenRobot}
      title="Brancher ou régler le robot"
    >
      <span class="status__dot" aria-hidden="true"></span>
      {label}
    </button>
  </div>
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

  .action--manual {
    background: rgb(113 96 210 / 16%);
    border-color: rgb(151 132 235 / 42%);
    color: #c9bdf5;
  }

  .action__icon--manual {
    background: linear-gradient(180deg, #8570e6, #6650c4);
    box-shadow: 0 4px 12px rgb(102 80 196 / 45%);
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

  .topright {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-left: auto;
    flex-wrap: wrap;
    justify-content: flex-end;
  }

  .standby-switch {
    border-color: #434959;
    background: #1e222d;
    color: #9da6b9;
  }

  .standby-switch:hover:not(:disabled) {
    background: #252b38;
    color: #cbd5e1;
  }

  .standby-switch--on {
    border-color: rgb(129 140 248 / 45%);
    background: rgb(99 102 241 / 18%);
    color: #c7d2fe;
  }

  .standby-switch--on:hover:not(:disabled) {
    background: rgb(99 102 241 / 28%);
  }

  .standby-switch[aria-checked='true'] .safety-switch__track {
    background: #6366f1;
  }

  .standby-switch--transition {
    opacity: 0.8;
    cursor: wait;
    animation: standby-pulse 1.5s infinite ease-in-out;
  }

  @keyframes standby-pulse {
    0%, 100% { opacity: 0.7; }
    50% { opacity: 1; }
  }

  .safety-switch {
    display: inline-flex;
    align-items: center;
    gap: 10px;
    min-height: 52px;
    padding: 6px 12px 6px 14px;
    border-radius: 999px;
    border: 1px solid rgb(88 196 128 / 42%);
    background: rgb(47 157 92 / 12%);
    color: #a6e6bb;
    font-family: inherit;
    cursor: pointer;
    transition:
      background 0.15s ease,
      border-color 0.15s ease,
      opacity 0.15s ease;
  }

  .safety-switch:hover:not(:disabled) {
    background: rgb(47 157 92 / 20%);
  }

  .safety-switch--off {
    border-color: rgb(226 100 110 / 48%);
    background: rgb(198 62 74 / 16%);
    color: #f3a7ae;
  }

  .safety-switch--off:hover:not(:disabled) {
    background: rgb(198 62 74 / 24%);
  }

  .safety-switch--unavailable {
    border-color: #454b59;
    background: #2a2e39;
    color: #8f97a8;
    opacity: 0.72;
    cursor: not-allowed;
  }

  .safety-switch--unavailable .safety-switch__track {
    background: #3a3f4a;
  }

  .safety-switch--unavailable .safety-switch__thumb {
    background: #c7ccd6;
  }

  .safety-switch:focus-visible {
    outline: 2px solid #cfe0f5;
    outline-offset: 3px;
  }

  .safety-switch__copy {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    line-height: 1.08;
    min-width: 0;
  }

  .safety-switch__label {
    font-size: 11.5px;
    font-weight: 850;
    letter-spacing: 0.07em;
    text-transform: uppercase;
  }

  .safety-switch__state {
    margin-top: 2px;
    font-size: 11px;
    font-weight: 650;
    opacity: 0.9;
  }

  .safety-switch__track {
    position: relative;
    width: 40px;
    height: 23px;
    flex: none;
    border-radius: 999px;
    border: 1px solid rgb(255 255 255 / 16%);
    background: rgb(0 0 0 / 26%);
    transition: background 0.15s ease;
  }

  .safety-switch[aria-checked='true'] .safety-switch__track {
    background: #3fbf72;
  }

  .safety-switch__thumb {
    position: absolute;
    top: 2px;
    left: 2px;
    width: 17px;
    height: 17px;
    border-radius: 50%;
    background: #f4f6fb;
    box-shadow: 0 1px 4px rgb(0 0 0 / 35%);
    transition: transform 0.16s ease;
  }

  .safety-switch[aria-checked='true'] .safety-switch__thumb {
    transform: translateX(17px);
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

  @media (max-width: 1180px) {
    .actions {
      order: 3;
      width: 100%;
      margin: 0;
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

    .safety-switch {
      min-height: 44px;
      padding: 4px 10px 4px 12px;
    }

    .safety-switch__label {
      font-size: 10.5px;
    }

    .safety-switch__state {
      font-size: 10px;
    }
  }
</style>
