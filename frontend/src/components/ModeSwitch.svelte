<script lang="ts">
  /**
   * Bascule simulation / robot réel.
   *
   * Le mode réel exige une autorisation explicite d'un adulte, tapée au
   * clavier, et une case à cocher de confirmation de zone dégagée. Aucun
   * mouvement n'est déclenché ici : ce composant ne fait que changer de mode.
   */
  import { app } from '../lib/stores/app.svelte';

  interface Props {
    onClose: () => void;
  }

  let { onClose }: Props = $props();

  /** Mot volontairement non trivial : évite l'activation accidentelle. */
  const CONFIRM_WORD = 'ROBOT';

  let word = $state('');
  let cleared = $state(false);
  let busy = $state(false);

  const canEnable = $derived(word.trim().toUpperCase() === CONFIRM_WORD && cleared);

  async function enable(): Promise<void> {
    if (!canEnable || busy) return;
    busy = true;
    await app.setMode('real', true);
    busy = false;
    onClose();
  }

  async function backToSimulation(): Promise<void> {
    await app.setMode('simulation', false);
    onClose();
  }
</script>

<div
  class="modal-backdrop"
  role="presentation"
  onclick={(e) => e.target === e.currentTarget && onClose()}
>
  <div class="modal" role="dialog" aria-modal="true" aria-labelledby="mode-title">
    <div class="modal__header">
      <span style="font-size:26px" aria-hidden="true">🤖</span>
      <h2 class="modal__title" id="mode-title">Choix du mode</h2>
    </div>

    <div class="modal__body">
      <p class="muted">Utilise ce panneau pour revenir en simulation.</p>

      <div class="message message--warn">
        <span class="message__icon" aria-hidden="true">⚠️</span>
        <span>
          <strong>Passage en mode robot réel.</strong> Le robot va réellement
          bouger. Vérifie que&nbsp;: la zone autour de lui est dégagée, un
          adulte est présent, la télécommande est à portée de main.
        </span>
      </div>

      <label class="check">
        <input type="checkbox" bind:checked={cleared} />
        <span>
          La zone est dégagée et un adulte est présent, capable d’arrêter le
          robot immédiatement.
        </span>
      </label>

      <label class="field">
        <span class="field__label">
          Pour confirmer, écris <strong>{CONFIRM_WORD}</strong> en majuscules&nbsp;:
        </span>
        <input
          class="input"
          type="text"
          bind:value={word}
          placeholder={CONFIRM_WORD}
          autocomplete="off"
        />
      </label>
    </div>

    <div class="modal__footer">
      <button type="button" class="btn btn--ghost" onclick={backToSimulation}>
        Revenir en simulation
      </button>
      <button type="button" class="btn btn--ghost" onclick={onClose}>Annuler</button>
      <button
        type="button"
        class="btn btn--danger"
        disabled={!canEnable || busy}
        onclick={enable}
      >
        Activer le robot réel
      </button>
    </div>
  </div>
</div>

<style>
  .check {
    display: flex;
    gap: 10px;
    align-items: flex-start;
    font-size: 14px;
    padding: 12px;
    border: 2px solid var(--ink-300);
    border-radius: var(--radius-m);
    cursor: pointer;
  }

  .check input {
    margin-top: 3px;
    width: 18px;
    height: 18px;
    flex: none;
  }

  .field {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .field__label {
    font-size: 14px;
    color: var(--ink-700);
  }
</style>