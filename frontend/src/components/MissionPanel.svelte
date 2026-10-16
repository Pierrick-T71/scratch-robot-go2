<script lang="ts">
  /**
   * Gestion des missions : créer, sauvegarder, rouvrir, supprimer.
   * Stockage 100 % local (localStorage), aucun compte, aucun envoi réseau.
   */
  import {
    listMissions,
    saveMission,
    deleteMission,
    MissionStorageError,
    type Mission,
  } from '../lib/programs/storage';
  import { app } from '../lib/stores/app.svelte';

  interface Props {
    /** API d'édition exposée par BlocklyEditor. */
    editor: { serialize: () => string; load: (xml: string) => void; clear: () => void } | null;
  }

  let { editor }: Props = $props();

  let missions = $state<Mission[]>(listMissions());
  let missionName = $state('');
  let feedback = $state<{ tone: 'ok' | 'error'; text: string } | null>(null);
  let pendingDelete = $state<Mission | null>(null);

  function refresh(): void {
    missions = listMissions();
  }

  function doSave(): void {
    if (!editor) return;
    try {
      const mission = saveMission(missionName, editor.serialize());
      missionName = '';
      refresh();
      feedback = { tone: 'ok', text: `Mission « ${mission.name} » enregistrée.` };
    } catch (error) {
      feedback = {
        tone: 'error',
        text:
          error instanceof MissionStorageError
            ? error.message
            : 'Impossible d’enregistrer la mission.',
      };
    }
  }

  function doOpen(mission: Mission): void {
    if (!editor) return;
    editor.load(mission.xml);
    app.setCommands([]);
    feedback = { tone: 'ok', text: `Mission « ${mission.name} » ouverte.` };
  }

  function confirmDelete(): void {
    if (!pendingDelete) return;
    deleteMission(pendingDelete.id);
    pendingDelete = null;
    refresh();
    feedback = { tone: 'ok', text: 'Mission supprimée.' };
  }

  function doNew(): void {
    editor?.clear();
    app.setCommands([]);
    feedback = { tone: 'ok', text: 'Nouveau programme prêt.' };
  }

  const formatted = $derived(
    missions.map((m) => ({ ...m, date: formatDate(m.updatedAt) })),
  );

  function formatDate(iso: string): string {
    return new Date(iso).toLocaleDateString('fr-FR', {
      day: '2-digit',
      month: '2-digit',
      year: '2-digit',
    });
  }
</script>

<section class="panel missions">
  <h2 class="panel__title">Mes missions</h2>

  <div class="missions__body">
    <div class="row">
      <input
        class="input grow"
        type="text"
        placeholder="Nom de la mission"
        maxlength="60"
        bind:value={missionName}
        onkeydown={(e) => e.key === 'Enter' && doSave()}
      />
      <button
        type="button"
        class="btn"
        onclick={doSave}
        disabled={!editor || missionName.trim().length === 0}
      >
        <span aria-hidden="true">💾</span> Enregistrer
      </button>
    </div>

    <button type="button" class="btn btn--ghost btn--sm" onclick={doNew}>
      <span aria-hidden="true">📄</span> Nouveau programme
    </button>

    {#if feedback}
      <div class="message message--{feedback.tone}" role="status">
        <span class="message__icon" aria-hidden="true">{feedback.tone === 'ok' ? '✅' : '⛔'}</span>
        <span>{feedback.text}</span>
      </div>
    {/if}

    {#if formatted.length === 0}
      <p class="muted">Aucune mission pour le moment. Donne un nom et enregistre.</p>
    {:else}
      <ul class="missions__list">
        {#each formatted as mission (mission.id)}
          <li class="missions__item">
            <div class="grow">
              <div class="missions__name">{mission.name}</div>
              <div class="muted">{mission.date}</div>
            </div>
            <button
              type="button"
              class="btn btn--ghost btn--sm"
              onclick={() => doOpen(mission)}
            >
              Ouvrir
            </button>
            <button
              type="button"
              class="btn btn--ghost btn--sm"
              onclick={() => (pendingDelete = mission)}
            >
              <span aria-hidden="true">🗑️</span>
            </button>
          </li>
        {/each}
      </ul>
    {/if}
  </div>
</section>

{#if pendingDelete}
  <div
    class="modal-backdrop"
    role="presentation"
    onclick={(e) => e.target === e.currentTarget && (pendingDelete = null)}
  >
    <div class="modal" role="dialog" aria-modal="true" aria-labelledby="del-title">
      <div class="modal__header">
        <span style="font-size:24px" aria-hidden="true">🗑️</span>
        <h2 class="modal__title" id="del-title">Supprimer la mission&nbsp;?</h2>
      </div>
      <div class="modal__body">
        <p>
          La mission « <strong>{pendingDelete.name}</strong> » sera effacée de
          cet appareil. Cette action est définitive.
        </p>
      </div>
      <div class="modal__footer">
        <button type="button" class="btn btn--ghost" onclick={() => (pendingDelete = null)}>
          Annuler
        </button>
        <button type="button" class="btn btn--danger" onclick={confirmDelete}>
          Supprimer
        </button>
      </div>
    </div>
  </div>
{/if}

<style>
  .missions__body {
    padding: 14px 16px;
    display: flex;
    flex-direction: column;
    gap: 11px;
    overflow-y: auto;
  }

  .missions__list {
    margin: 0;
    padding: 0;
    list-style: none;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .missions__item {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 11px;
    background: var(--ink-100);
    border-radius: var(--radius-s);
  }

  .missions__name {
    font-weight: 700;
    font-size: 14px;
  }
</style>