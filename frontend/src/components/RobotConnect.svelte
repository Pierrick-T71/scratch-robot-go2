<script lang="ts">
  /**
   * Branchement d'un robot réel.
   *
   * L'enfant saisit l'adresse du robot et lance un test. Le test envoie
   * `Sit()` — la posture assise. C'est délibéré : elle abaisse le robot et le
   * ramène à un état stable. Un robot debout qui bascule fait mal ; un robot
   * assis non. Elle prouve surtout que le canal d'ALLER est accepté, pas
   * seulement la réception d'un état.
   *
   * ⚠️ CE BOUTON FAIT BOUGER LE ROBOT. Il est distinct du « Démarrer » pour
   * que la distinction soit visible, pas seulement techniquement cachée.
   */
  import { api, ServiceError } from '../lib/api/client';

  interface Props {
    onClose?: () => void;
  }
  let { onClose }: Props = $props();

  let robotIp = $state('172.16.8.11');
  let lancerTest = $state(true);
  let enCours = $state(false);
  let resultat = $state<{
    ok: boolean;
    titre: string;
    details: string[];
  } | null>(null);

  /** Un controle simple avant d'envoyer quoi que ce soit. */
  const ipValide = $derived(/^(\d{1,3}\.){3}\d{1,3}$/.test(robotIp.trim()));

  async function connecter(): Promise<void> {
    if (!ipValide || enCours) return;
    enCours = true;
    resultat = null;
    try {
      const rapport = await api.connectRobot(robotIp.trim(), lancerTest);
      const details: string[] = [];
      if (rapport.commande_envoyee) {
        details.push(`Commande envoyée : ${rapport.commande_envoyee}`);
      }
      if (!lancerTest) {
        details.push(
          'Aucun mouvement envoyé : le robot a répondu, mais aucune consigne.',
        );
      }
      resultat = {
        ok: true,
        titre: 'Robot connecté',
        details,
      };
    } catch (error) {
      const message =
        error instanceof ServiceError ? error.message : 'Connexion impossible.';
      // Le service renvoie un message déjà rédigé pour un enfant : on ne le
      // remplace pas, on ne le surcharge pas non plus.
      resultat = {
        ok: false,
        titre: 'Robot introuvable',
        details: message.split('. '),
      };
    } finally {
      enCours = false;
    }
  }

  async function deconnecter(): Promise<void> {
    enCours = true;
    try {
      await api.disconnectRobot();
      resultat = {
        ok: true,
        titre: 'Retour en simulation',
        details: ['Le robot ne reçoit plus de programme.'],
      };
    } catch {
      resultat = {
        ok: false,
        titre: 'Déconnexion impossible',
        details: ['Le service ne répond pas.'],
      };
    } finally {
      enCours = false;
    }
  }
</script>

<section class="robot" aria-label="Robot réel">
  <h2 class="robot__title">Robot réel</h2>

  <p class="robot__intro">
    En simulation, le robot est imité par l'ordinateur. Pour piloter le vrai
    robot, indique son adresse.
  </p>

  <div class="robot__champ">
    <label class="robot__label" for="robot-ip">Adresse du robot</label>
    <input
      id="robot-ip"
      class="robot__input"
      type="text"
      inputmode="decimal"
      bind:value={robotIp}
      placeholder="172.16.8.11"
      autocomplete="off"
      spellcheck="false"
      disabled={enCours}
    />
  </div>

  <label class="robot__opt">
    <input type="checkbox" bind:checked={lancerTest} disabled={enCours} />
    <span>
      Asseoir le robot pour vérifier qu'il répond
      <small>Cette action fait bouger le robot.</small>
    </span>
  </label>

  <div class="robot__actions">
    <button
      type="button"
      class="btn btn--primary"
      onclick={connecter}
      disabled={enCours || !ipValide}
    >
      {enCours ? 'Connexion…' : 'Tester le robot'}
    </button>
    <button
      type="button"
      class="btn btn--ghost"
      onclick={deconnecter}
      disabled={enCours}
    >
      Revenir en simulation
    </button>
  </div>

  {#if !ipValide && robotIp.trim().length > 0}
    <p class="robot__erreur" role="alert">
      Une adresse ressemble à 172.16.13.100.
    </p>
  {/if}

  {#if resultat}
    <div
      class="robot__resultat"
      class:robot__resultat--ok={resultat.ok}
      role="status"
    >
      <strong>{resultat.titre}</strong>
      {#each resultat.details as detail}
        <p>{detail}</p>
      {/each}
    </div>
  {/if}

  {#if onClose}
    <button type="button" class="btn btn--ghost btn--sm" onclick={onClose}>
      Fermer
    </button>
  {/if}
</section>

<style>
  .robot {
    display: flex;
    flex-direction: column;
    gap: 10px;
    padding: 12px;
    background: var(--surface-2);
    border: 1px solid var(--line);
    border-radius: var(--radius-lg);
  }

  .robot__title {
    margin: 0;
    font-size: 13px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: var(--ink-600);
  }

  .robot__intro {
    margin: 0;
    font-size: 12px;
    line-height: 1.5;
    color: var(--ink-500);
  }

  .robot__champ {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .robot__label {
    font-size: 12px;
    font-weight: 600;
    color: var(--ink-600);
  }

  .robot__input {
    padding: 7px 10px;
    font-size: 14px;
    font-family: var(--font-mono, monospace);
    border: 1px solid var(--line);
    border-radius: var(--radius-sm);
    background: var(--surface);
    color: var(--ink-900);
  }

  .robot__input:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 1px;
  }

  .robot__opt {
    display: flex;
    align-items: flex-start;
    gap: 8px;
    font-size: 12px;
    color: var(--ink-700);
    cursor: pointer;
  }

  .robot__opt small {
    display: block;
    font-size: 11px;
    color: var(--ink-500);
  }

  .robot__actions {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }

  .robot__erreur {
    margin: 0;
    font-size: 12px;
    color: var(--danger);
  }

  .robot__resultat {
    padding: 9px 11px;
    font-size: 12px;
    line-height: 1.5;
    border-radius: var(--radius-md);
    background: var(--surface);
    border: 1px solid var(--danger);
    color: var(--ink-800);
  }

  .robot__resultat--ok {
    border-color: var(--success, #16a34a);
  }

  .robot__resultat p {
    margin: 3px 0 0;
    color: var(--ink-600);
  }
</style>