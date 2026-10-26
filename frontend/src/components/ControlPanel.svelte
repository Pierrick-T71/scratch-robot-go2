<script lang="ts">
  /**
   * Zone de controle : vérification, démarrage, arrêt, progression, messages.
   *
   * Le bouton « Arrêter » est TOUJOURS visible et actif pendant une
   * exécution. Il ne garantit pas l'arrêt physique : c'est le service qui
   * reste responsable de l'arrêt réel.
   */
  import { app } from '../lib/stores/app.svelte';

  interface Props {
    onCheck: () => void;
    onStart: () => void;
  }

  let { onCheck, onStart }: Props = $props();

  const steps = $derived(app.steps);
  // Une étape bloquée a été traitée par le programme (elle n'a pas été
  // faite, mais elle ne sera pas rejouée) : elle compte dans l'avancement.
  const doneCount = $derived(
    steps.filter((s) => s.state === 'done' || s.state === 'blocked').length,
  );
  const percent = $derived(
    steps.length === 0 ? 0 : Math.round((doneCount / steps.length) * 100),
  );

  const stateLabel = $derived(
    {
      idle: 'En attente',
      checking: 'Vérification…',
      ready: 'Prêt à démarrer',
      starting: 'Démarrage…',
      running: 'Programme en cours',
      stopping: 'Arrêt en cours…',
      done: 'Terminé',
      stopped: 'Arrêté',
      error: 'Problème',
    }[app.execution],
  );

  const canStart = $derived(
    app.execution === 'ready' && !app.isBusy,
  );

  const summary = $derived(app.report?.summary ?? null);
</script>

<section class="panel control">
  <h2 class="panel__title">Contrôle du programme</h2>

  <div class="control__body">
    <!-- Progression -->
    {#if app.report}
      <div class="stack">
        <div class="row">
          <span class="badge badge--{app.execution === 'running' ? 'ok' : 'neutral'}">
            {stateLabel}
          </span>
          {#if summary}
            <span class="muted">
              {summary.stepCount} pas · environ {summary.estimatedSeconds} s
            </span>
          {/if}
        </div>

        <div class="progress" role="progressbar" aria-valuenow={percent} aria-valuemin="0" aria-valuemax="100">
          <div class="progress__fill" style="width: {percent}%"></div>
        </div>
      </div>
    {/if}

    <!-- Message principal -->
    {#if app.notice}
      <div class="message message--{app.notice.tone}" role="status" aria-live="polite">
        <span class="message__icon" aria-hidden="true">
          {app.notice.tone === 'ok' ? '✅' : app.notice.tone === 'warn' ? '⚠️' : '⛔'}
        </span>
        <span>{app.notice.message}</span>
      </div>
    {/if}

    <!-- Liste des erreurs de validation -->
    {#if app.report && app.report.issues.length > 0}
      <ul class="issues">
        {#each app.report.issues as issue (issue.message + String(issue.line ?? ''))}
          <li class="issues__item">{issue.message}</li>
        {/each}
      </ul>
    {/if}

    <!-- Boutons -->
    <div class="control__buttons">
      <button type="button" class="btn btn--ghost" onclick={onCheck} disabled={app.isBusy}>
        <span aria-hidden="true">🔍</span> Vérifier mon programme
      </button>
      <button type="button" class="btn btn--ok" onclick={onStart} disabled={!canStart}>
        <span aria-hidden="true">▶️</span> Démarrer
      </button>
      <button
        type="button"
        class="btn btn--danger"
        onclick={() => app.requestStop()}
        disabled={!app.isBusy}
      >
        <span aria-hidden="true">⛔</span> Arrêter
      </button>
    </div>

    <p class="control__reassurance">
      En cas de doute, utilise la télécommande du robot ou appuie sur son
      bouton d’arrêt physique.
    </p>

    <!-- Étapes -->
    {#if steps.length > 0}
      <div class="control__steps">
        <h3 class="control__steps-title">Étapes du programme</h3>
        <ul class="steps">
          {#each steps as step (step.index)}
            <li class="steps__item steps__item--{step.state}">
              <span class="steps__index">
                {step.state === 'done'
                  ? '✓'
                  : step.state === 'blocked'
                    ? '!'
                    : step.state === 'running'
                      ? '▶'
                      : step.index + 1}
              </span>
              <span class="grow">{step.label}</span>
              {#if step.outcome}
                <span
                  class="steps__outcome"
                  class:steps__outcome--long={step.outcome.length > 28}
                >{step.outcome}</span>
              {/if}
            </li>
          {/each}
        </ul>
      </div>
    {/if}
  </div>
</section>

<style>
  .control {
    display: flex;
    flex-direction: column;
    /* Pas de défilement interne : c'est la colonne latérale qui défile.
       Sans `flex: none`, le corps s'effondre à 0 px dans une colonne flex. */
    flex: none;
  }

  .control__body {
    padding: 14px 16px;
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .control__buttons {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 9px;
  }

  .control__buttons .btn--danger {
    grid-column: 1 / -1;
  }

  .control__reassurance {
    margin: 0;
    font-size: 12px;
    color: var(--ink-500);
    line-height: 1.4;
  }

  .control__steps-title {
    margin: 4px 0 0;
    font-size: 13px;
    font-weight: 700;
    color: var(--ink-700);
  }

  .issues {
    margin: 0;
    padding-left: 20px;
    display: flex;
    flex-direction: column;
    gap: 4px;
    font-size: 13px;
    color: var(--danger);
  }

  .control__steps {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
</style>