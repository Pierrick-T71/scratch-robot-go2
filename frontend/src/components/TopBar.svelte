<script lang="ts">
  /** Barre supérieure : identité, projet, état de connexion, mode, aide. */
  import { app } from '../lib/stores/app.svelte';

  interface Props {
    projectName: string;
    onHelp: () => void;
  }

  let { projectName, onHelp }: Props = $props();

  const connection = $derived(
    app.status.connected
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
    <div>
      <div class="topbar__name">GO2 Scratch</div>
      <div class="topbar__tagline">Programme ton robot</div>
    </div>
  </div>

  <div class="topbar__project">
    <span class="muted">Projet&nbsp;:</span>
    <strong>{projectName}</strong>
  </div>

  <div class="topbar__badges">
    <span class="badge badge--{mode.tone}">
      <span class="badge__dot" aria-hidden="true"></span>
      {mode.text}
    </span>
    <span class="badge badge--{connection.tone}">
      <span class="badge__dot" aria-hidden="true"></span>
      {connection.text}
    </span>
  </div>

  <button type="button" class="btn btn--ghost btn--sm" onclick={onHelp}>
    <span aria-hidden="true">❓</span> Aide
  </button>
</header>

<style>
  .topbar {
    display: flex;
    align-items: center;
    gap: 18px;
    padding: 10px 18px;
    background: var(--paper);
    border-bottom: 1px solid var(--ink-300);
    box-shadow: var(--shadow-s);
    flex: none;
  }

  .topbar__brand {
    display: flex;
    align-items: center;
    gap: 10px;
  }

  .topbar__logo {
    font-size: 30px;
    line-height: 1;
  }

  .topbar__name {
    font-size: 19px;
    font-weight: 800;
    color: var(--brand-600);
    letter-spacing: -0.3px;
  }

  .topbar__tagline {
    font-size: 11px;
    color: var(--ink-500);
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }

  .topbar__project {
    font-size: 14px;
    color: var(--ink-700);
  }

  .topbar__badges {
    margin-left: auto;
    display: flex;
    gap: 8px;
  }
</style>