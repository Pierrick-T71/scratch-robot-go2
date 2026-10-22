<script lang="ts">
  /** Barre supérieure : identité, état de connexion, mode, aide, réglages. */
  import { app } from '../lib/stores/app.svelte';

  interface Props {
    onHelp: () => void;
    onSettings: () => void;
  }

  let { onHelp, onSettings }: Props = $props();

  const connection = $derived(
    app.status.safetyReason
      ? { tone: 'danger' as const, text: 'Robot à l’arrêt' }
      : app.status.connected
        ? { tone: 'ok' as const, text: 'Robot connecté' }
        : { tone: 'danger' as const, text: 'Robot non connecté' },
  );

  const mode = $derived(
    app.status.mode === 'simulation'
      ? { tone: 'neutral' as const, text: 'Mode simulation' }
      : { tone: 'warn' as const, text: 'Mode robot réel' },
  );
</script>

<header class="topbar">
  <div class="topbar__brand">
    <span class="topbar__logo" aria-hidden="true">🐕</span>
    <div class="topbar__names">
      <span class="topbar__name">GO2 Scratch</span>
      <span class="topbar__tagline">Programme ton robot</span>
    </div>
  </div>

  <div class="topbar__badges">
    <span class="badge badge--{mode.tone}">
      <span class="badge__dot" aria-hidden="true"></span>
      {mode.text}
    </span>
    <span class="badge badge--{connection.tone}">
      <span
        class="badge__dot"
        class:badge__dot--live={app.status.connected && app.isBusy}
        aria-hidden="true"
      ></span>
      {connection.text}
    </span>
    {#if app.isBusy}
      <span class="badge badge--info">
        <span class="badge__dot badge__dot--live" aria-hidden="true"></span>
        En cours
      </span>
    {/if}
  </div>

  <div class="topbar__actions">
    <button
      type="button"
      class="btn btn--ghost btn--sm"
      onclick={onSettings}
      title="Réglages du robot et préférences"
    >
      <span aria-hidden="true">⚙️</span> Configuration
    </button>
    <button
      type="button"
      class="btn btn--ghost btn--sm"
      onclick={onHelp}
      title="Guide d'aide"
    >
      <span aria-hidden="true">❓</span> Aide
    </button>
  </div>
</header>

<style>
  .topbar {
    display: flex;
    align-items: center;
    gap: 16px;
    height: var(--topbar-h);
    padding: 0 var(--gutter);
    background: rgb(255 255 255 / 85%);
    backdrop-filter: blur(10px);
    border-bottom: 1px solid var(--line);
    flex: none;
    position: relative;
    z-index: 10;
  }

  /* Liseré coloré sous la barre : signature visuelle discrète. */
  .topbar::after {
    content: '';
    position: absolute;
    inset: auto 0 -1px 0;
    height: 2px;
    background: linear-gradient(
      90deg,
      var(--brand-500) 0%,
      var(--brand-400) 35%,
      var(--accent-500) 100%
    );
  }

  .topbar__brand {
    display: flex;
    align-items: center;
    gap: 11px;
    flex: none;
  }

  .topbar__logo {
    font-size: 27px;
    line-height: 1;
    filter: drop-shadow(0 2px 4px rgb(15 23 41 / 18%));
  }

  .topbar__names {
    display: flex;
    flex-direction: column;
    line-height: 1.15;
  }

  .topbar__name {
    font-size: 18px;
    font-weight: 850;
    letter-spacing: -0.03em;
    background: linear-gradient(96deg, var(--brand-600), var(--brand-400));
    -webkit-background-clip: text;
    background-clip: text;
    color: transparent;
  }

  .topbar__tagline {
    font-size: 10.5px;
    font-weight: 700;
    color: var(--ink-400);
    text-transform: uppercase;
    letter-spacing: 0.09em;
  }

  .topbar__badges {
    margin-left: auto;
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
  }

  .topbar__actions {
    display: flex;
    gap: 8px;
    flex: none;
  }

  @media (max-width: 900px) {
    .topbar__tagline {
      display: none;
    }
  }

  @media (max-width: 700px) {
    .topbar__badges {
      display: none;
    }
  }
</style>