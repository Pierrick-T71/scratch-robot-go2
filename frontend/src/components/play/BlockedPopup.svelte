<script lang="ts">
  /**
   * Fenêtre centrale quand le service refuse un pas faute de place.
   *
   * Elle existe parce qu'un message compact dans l'en-tête pouvait être
   * coupé : ici le texte complet est affiché, avec un bouton Fermer.
   */
  import { onMount } from 'svelte';

  interface Props {
    title: string;
    message: string;
    /** `blocked` : le pas n'a pas commencé. `stopped` : arrêt pendant le pas. */
    kind: 'blocked' | 'stopped';
    onClose: () => void;
  }

  let { title, message, kind, onClose }: Props = $props();

  const subtitle = $derived(
    kind === 'blocked' ? 'Le robot n’a pas bougé' : 'Le robot s’est arrêté à temps',
  );
  const hint = $derived(
    kind === 'blocked'
      ? 'Écarte l’obstacle ou déplace le robot, puis relance le programme.'
      : 'Écarte l’obstacle, puis relance le programme.',
  );

  let dialogue = $state<HTMLDivElement | null>(null);

  onMount(() => {
    dialogue?.querySelector<HTMLButtonElement>('button')?.focus();
  });
</script>

<div class="modal-backdrop" role="presentation">
  <div
    class="modal"
    role="alertdialog"
    aria-modal="true"
    aria-labelledby="blocked-title"
    aria-describedby="blocked-message"
    bind:this={dialogue}
  >
    <div class="modal__header">
      <span class="modal__emoji" aria-hidden="true">🚧</span>
      <div>
        <h2 class="modal__title" id="blocked-title">{title}</h2>
        <p class="modal__subtitle">{subtitle}</p>
      </div>
    </div>

    <div class="modal__body">
      <p class="blocked__message" id="blocked-message">{message}</p>
      <p class="blocked__hint">{hint}</p>
    </div>

    <div class="modal__footer">
      <button type="button" class="btn btn--ok" onclick={onClose}>
        Fermer
      </button>
    </div>
  </div>
</div>

<style>
  .blocked__message {
    margin: 0;
    white-space: pre-wrap;
    overflow-wrap: anywhere;
    max-height: 42vh;
    overflow-y: auto;
    font-size: 16px;
    line-height: 1.45;
  }

  .blocked__hint {
    margin: 12px 0 0;
    color: var(--ink-500);
    font-size: 13.5px;
    line-height: 1.4;
  }
</style>
