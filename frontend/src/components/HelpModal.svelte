<script lang="ts">
  /** Guide d'aide intégré, en français, destiné aux enfants et aux animateurs. */
  interface Props {
    onClose: () => void;
  }

  let { onClose }: Props = $props();
</script>

<div
  class="modal-backdrop"
  role="presentation"
  onclick={(e) => e.target === e.currentTarget && onClose()}
>
  <div class="modal" role="dialog" aria-modal="true" aria-labelledby="help-title">
    <div class="modal__header">
      <span style="font-size:26px" aria-hidden="true">❓</span>
      <h2 class="modal__title" id="help-title">Comment ça marche&nbsp;?</h2>
      <button
        type="button"
        class="btn btn--ghost btn--sm"
        style="margin-left:auto"
        onclick={onClose}
      >
        Fermer
      </button>
    </div>

    <div class="modal__body">
      <h3 class="help__h">1. Compose ton programme</h3>
      <p>
        Prends un bloc dans la palette à gauche (par exemple
        <span class="chip chip--movement">Avancer de 50 cm</span>) et
        <strong>accroche-le sous le bloc de départ</strong>. Tu peux changer les
        nombres en cliquant dessus.
      </p>

      <h3 class="help__h">2. Vérifie</h3>
      <p>
        Clique sur <strong>Vérifier mon programme</strong>. Si quelque chose ne
        va pas, un message t’explique quoi corriger.
      </p>

      <h3 class="help__h">3. Démarre</h3>
      <p>
        Clique sur <strong>Démarrer</strong>. La liste de droite montre les
        étapes au fur et à mesure.
      </p>

      <h3 class="help__h">4. En cas de problème</h3>
      <p>
        Clique sur <strong>Arrêter</strong>, et si le robot bouge encore,
        utilise la <strong>télécommande</strong> du robot ou son
        <strong>bouton d’arrêt physique</strong>.
      </p>

      <div class="message message--warn">
        <span class="message__icon" aria-hidden="true">⚠️</span>
        <span>
          Un adulte doit toujours être présent et la zone autour du robot
          doit être dégagée avant tout démarrage en mode réel.
        </span>
      </div>

      <h3 class="help__h">Simulation ou robot réel&nbsp;?</h3>
      <p>
        Au départ, l’application est en <strong>simulation</strong> : aucun
        vrai mouvement. Le mode <strong>robot réel</strong> ne peut être activé
        que par un adulte, et seulement si la zone est dégagée.
      </p>
    </div>
  </div>
</div>

<style>
  .help__h {
    margin: 6px 0 0;
    font-size: 16px;
    color: var(--brand-600);
  }

  .help__h:first-child {
    margin-top: 0;
  }

  .chip {
    display: inline-block;
    padding: 2px 9px;
    border-radius: 999px;
    font-size: 13px;
    font-weight: 700;
    color: #fff;
  }

  .chip--movement {
    background: var(--cat-movement);
  }
</style>