<script lang="ts">
  /**
   * Guide d'aide intégré pour Optimus.
   * Explique la programmation en pièces de puzzle, le réglage des durées/angles,
   * le lancement avec le drapeau vert, la suppression et le mode manuel.
   */
  import Icon from './play/Icon.svelte';

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
  <div class="modal help-modal" role="dialog" aria-modal="true" aria-labelledby="help-title">
    <div class="modal__header">
      <span class="help-modal__icon" aria-hidden="true">
        <Icon name="sparkle" size={20} />
      </span>
      <div>
        <h2 class="modal__title" id="help-title">Comment programmer Optimus&nbsp;?</h2>
        <p class="modal__subtitle">Guide d'aide pas à pas pour petits et grands</p>
      </div>
      <button
        type="button"
        class="help-close-btn"
        onclick={onClose}
        aria-label="Fermer le guide d'aide"
        title="Fermer"
      >
        ✕
      </button>
    </div>

    <div class="modal__body help-modal__body">
      <!-- Étape 1 -->
      <section class="help-card">
        <div class="help-card__badge help-card__badge--1">1</div>
        <div class="help-card__content">
          <h3 class="help-card__title">Assemble tes pièces de puzzle</h3>
          <p class="help-card__text">
            Dans la <strong>Bibliothèque de blocs</strong>, choisis un mouvement ou une action
            (<em>Avancer</em>, <em>Tourner</em>, <em>Saluer</em>, <em>Faire un cœur</em>...).
            Clique dessus ou glisse-le dans la zone <strong>Mon Programme</strong> en bas.
            Les blocs s'emboîtent automatiquement comme de vraies pièces de puzzle !
          </p>
        </div>
      </section>

      <!-- Étape 2 -->
      <section class="help-card">
        <div class="help-card__badge help-card__badge--2">2</div>
        <div class="help-card__content">
          <h3 class="help-card__title">Règle les durées et les angles</h3>
          <p class="help-card__text">
            Sur les pièces de déplacement (bleues et violettes), clique sur la petite bulle blanche
            pour choisir le temps de marche (<strong>1 s, 2 s, 3 s...</strong>) ou l'angle de
            rotation (<strong>45°, 90°, 180°...</strong>).
          </p>
        </div>
      </section>

      <!-- Étape 3 -->
      <section class="help-card">
        <div class="help-card__badge help-card__badge--3">3</div>
        <div class="help-card__content">
          <h3 class="help-card__title">Lance ton programme</h3>
          <p class="help-card__text">
            Clique sur le <strong>drapeau vert</strong> dans « Mon Programme ».
            Optimus effectue chaque action dans l'ordre, et la pièce en train d'être exécutée
            s'illumine en temps réel !
          </p>
        </div>
      </section>

      <!-- Étape 4 -->
      <section class="help-card">
        <div class="help-card__badge help-card__badge--4">4</div>
        <div class="help-card__content">
          <h3 class="help-card__title">Déplace ou supprime un bloc</h3>
          <p class="help-card__text">
            Pour réorganiser l'ordre, glisse simplement un bloc vers la gauche ou la droite.<br />
            Pour supprimer une pièce, reprends-la et glisse-la vers la bibliothèque ou sur l'icône de la corbeille.
          </p>
        </div>
      </section>

      <!-- Étape 5 -->
      <section class="help-card">
        <div class="help-card__badge help-card__badge--5">5</div>
        <div class="help-card__content">
          <h3 class="help-card__title">Mode manuel & Télécommande smartphone</h3>
          <p class="help-card__text">
            Clique sur le bouton <strong>Mode manuel</strong> (manette en haut) pour piloter Optimus au clavier
            (<strong>ZQSD</strong> pour bouger, <strong>Shift + Z</strong> pour sprinter, <strong>Espace</strong> pour sauter),
            ou scanne le <strong>QR code</strong> avec un smartphone pour le diriger depuis l'écran tactile !
          </p>
        </div>
      </section>

      <!-- Sécurité -->
      <div class="help-alert">
        <span class="help-alert__icon" aria-hidden="true">⚠️</span>
        <div class="help-alert__text">
          <strong>Sécurité importante :</strong> À tout moment, clique sur le gros bouton rouge
          <strong>Arrêter</strong> pour stopper immédiatement Optimus.
          En mode réel, un adulte doit toujours être présent et s'assurer que la zone autour du robot est bien dégagée.
        </div>
      </div>
    </div>

    <div class="modal__footer">
      <button
        type="button"
        class="help-ok-btn"
        onclick={onClose}
      >
        C'est compris !
      </button>
    </div>
  </div>
</div>

<style>
  .help-modal {
    width: min(640px, 94vw);
    max-height: 86vh;
    border: 1px solid #363c4e;
    background: #1f232e;
    border-radius: 20px;
    box-shadow: 0 20px 50px rgba(0, 0, 0, 0.45);
    color: #e4e9f5;
  }

  .help-modal__icon {
    display: grid;
    place-items: center;
    width: 38px;
    height: 38px;
    flex: none;
    border-radius: 12px;
    background: linear-gradient(180deg, #3b82f6, #1d4ed8);
    color: #ffffff;
    box-shadow: 0 4px 12px rgba(59, 130, 246, 0.35);
  }

  .help-close-btn {
    display: grid;
    place-items: center;
    width: 32px;
    height: 32px;
    margin-left: auto;
    border: 1px solid #3b4255;
    border-radius: 10px;
    background: rgba(255, 255, 255, 0.05);
    color: #94a3b8;
    font-size: 14px;
    cursor: pointer;
    transition: background 0.15s, color 0.15s;
  }

  .help-close-btn:hover {
    background: rgba(255, 255, 255, 0.12);
    color: #ffffff;
  }

  .help-modal__body {
    display: flex;
    flex-direction: column;
    gap: 12px;
    padding: 16px 20px;
    overflow-y: auto;
  }

  .help-card {
    display: flex;
    align-items: flex-start;
    gap: 14px;
    padding: 12px 14px;
    border: 1px solid #2e3444;
    border-radius: 14px;
    background: rgba(15, 23, 42, 0.45);
  }

  .help-card__badge {
    display: grid;
    place-items: center;
    width: 28px;
    height: 28px;
    flex: none;
    border-radius: 999px;
    font-size: 13px;
    font-weight: 800;
    color: #ffffff;
    margin-top: 1px;
  }

  .help-card__badge--1 {
    background: #3b82f6;
  }

  .help-card__badge--2 {
    background: #8b5cf6;
  }

  .help-card__badge--3 {
    background: #10b981;
  }

  .help-card__badge--4 {
    background: #f59e0b;
  }

  .help-card__badge--5 {
    background: #ec4899;
  }

  .help-card__content {
    flex: 1;
    min-width: 0;
  }

  .help-card__title {
    margin: 0 0 3px;
    font-size: 14.5px;
    font-weight: 750;
    color: #f1f5f9;
  }

  .help-card__text {
    margin: 0;
    font-size: 13px;
    line-height: 1.45;
    color: #94a3b8;
  }

  .help-card__text strong {
    color: #e2e8f0;
  }

  .help-card__text em {
    color: #93c5fd;
    font-style: normal;
    font-weight: 600;
  }

  .help-alert {
    display: flex;
    align-items: flex-start;
    gap: 10px;
    padding: 12px 14px;
    border: 1px solid rgba(245, 158, 11, 0.35);
    border-radius: 14px;
    background: rgba(245, 158, 11, 0.1);
    color: #fef3c7;
    font-size: 12.5px;
    line-height: 1.4;
  }

  .help-alert__icon {
    font-size: 18px;
    line-height: 1;
    flex: none;
  }

  .help-alert__text strong {
    color: #fbbf24;
  }

  .help-ok-btn {
    padding: 8px 22px;
    border: 1px solid #3b82f6;
    border-radius: 999px;
    background: linear-gradient(180deg, #3b82f6, #2563eb);
    color: #ffffff;
    font: inherit;
    font-size: 13.5px;
    font-weight: 700;
    cursor: pointer;
    box-shadow: 0 4px 12px rgba(37, 99, 235, 0.35);
    transition: filter 0.15s, transform 0.12s;
  }

  .help-ok-btn:hover {
    filter: brightness(1.1);
    transform: translateY(-1px);
  }

  .help-ok-btn:active {
    transform: translateY(0);
  }
</style>
