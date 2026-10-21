<script lang="ts">
  /**
   * Vue « robot » : la scène, l'état réel et les raccourcis.
   *
   * La scène reprend celle du lidar : le Go2 au milieu d'une grille sombre.
   * Sans la carte, elle sert de vue du robot ; le bouton lidar ajoute les
   * cubes du capteur. Le robot marche quand un déplacement est en cours.
   * Les valeurs affichées (batterie, position) viennent du service — et
   * restent « — » quand aucune mesure n'existe.
   */
  import Icon from './Icon.svelte';
  import LidarScene from './LidarScene.svelte';
  import type { LidarVolume, RobotStatus } from '../../lib/api/client';
  import { api } from '../../lib/api/client';
  import { SERVICE_URL } from '../../lib/robot/limits';

  interface Props {
    status: RobotStatus;
    /** Un bloc de déplacement tourne : les pattes doivent marcher. */
    walking?: boolean;
    onOpenRobot: () => void;
  }

  let { status, walking = false, onOpenRobot }: Props = $props();

  /** La caméra du robot est-elle à l'écran ? */
  let camera = $state(false);
  /** Le flux a-t-il échoué (robot non branché, pas de caméra) ? */
  let cameraFailed = $state(false);
  /** La vue du capteur lidar est-elle à l'écran ? */
  let lidar = $state(false);
  /** Cases occupées de la carte du lidar, en mètres autour du robot. */
  let cases = $state<[number, number][]>([]);
  /** Le volume de voxels, pour la vue en 3D. */
  let volume = $state<LidarVolume | null>(null);

  /**
   * Adresse du flux MJPEG.
   *
   * Le service relaie les images du robot : la clé de chiffrement ne quitte
   * jamais la machine qui parle au robot.
   */
  const cameraUrl = `${SERVICE_URL}/api/robot/camera`;

  /**
   * La carte du lidar, rafraîchie tant que la vue est ouverte.
   *
   * Le lidar ne publie sa carte que lorsque le robot est DEBOUT : on le
   * dit plutôt que d'afficher une carte vide sans explication.
   */
  $effect(() => {
    if (!lidar) {
      cases = [];
      volume = null;
      return;
    }
    let vivant = true;
    const boucle = async (): Promise<void> => {
      while (vivant) {
        try {
          const resultat = await api.getLidar();
          if (!vivant) return;
          cases = resultat.points;
          volume = resultat.volume;
        } catch {
          if (!vivant) return;
          cases = [];
          volume = null;
        }
        await new Promise((resolve) => setTimeout(resolve, 400));
      }
    };
    void boucle();
    return () => {
      vivant = false;
    };
  });

  const battery = $derived(
    status.batteryPercent === null
      ? '—'
      : `${Math.round(status.batteryPercent)} %`,
  );

  /**
   * Posture du robot, en mots simples pour l'enfant.
   *
   * `null` quand le service ne la connaît pas : on n'invente pas un « debout »
   * qui n'a pas été demandé.
   */
  const posture = $derived(
    status.posture === 'stand'
      ? 'Debout'
      : status.posture === 'sit'
        ? 'Assis'
        : status.posture === 'balance'
          ? 'Stabilisé'
          : status.posture === 'lie_down'
            ? 'Allongé'
            : null,
  );

  /** Bascule entre le robot 3D et la caméra du robot. */
  function toggleCamera(): void {
    camera = !camera;
    cameraFailed = false;
    lidar = false;
  }

  /** Bascule entre le robot 3D et la vue du capteur lidar. */
  function toggleLidar(): void {
    lidar = !lidar;
    camera = false;
    cameraFailed = false;
  }
</script>

<aside class="robot" aria-label="État du robot">
  <div class="scene">
    <div class="scene__robot">
      <LidarScene volume={lidar ? volume : null} {walking} interactive={lidar} />
    </div>

    {#if camera}
      {#if cameraFailed}
        <div class="scene__absent">
          <Icon name="camera" size={30} />
          <p>La caméra n’est pas disponible pour le moment.</p>
        </div>
      {:else}
        <!-- Le flux vient du service, qui relaie les images du robot. -->
        <img
          class="scene__camera"
          src={cameraUrl}
          alt="Vue de la caméra du robot"
          onerror={() => (cameraFailed = true)}
        />
      {/if}
    {/if}

    {#if lidar && cases.length === 0 && !volume}
      <p class="scene__note">
        Le capteur n’envoie rien : le robot doit être debout.
      </p>
    {/if}

    <button
      type="button"
      class="scene__btn scene__btn--left"
      class:scene__btn--on={lidar}
      aria-label={lidar ? 'Revenir au robot 3D' : 'Voir le capteur lidar'}
      title={lidar ? 'Robot 3D' : 'Capteur lidar'}
      aria-pressed={lidar}
      onclick={toggleLidar}
    >
      <Icon name="radar" size={18} />
    </button>

    <button
      type="button"
      class="scene__btn scene__btn--right"
      class:scene__btn--on={camera}
      aria-label={camera ? 'Revenir au robot 3D' : 'Voir la caméra du robot'}
      title={camera ? 'Robot 3D' : 'Caméra du robot'}
      aria-pressed={camera}
      onclick={toggleCamera}
    >
      <Icon name="camera" size={18} />
    </button>

    <span class="scene__badge" class:scene__badge--on={status.connected}>
      <span class="scene__dot" aria-hidden="true"></span>
      {camera
        ? 'Caméra du robot'
        : lidar
          ? 'Capteur lidar'
          : status.mode === 'real'
            ? 'Robot réel'
            : 'Simulation'}
    </span>
  </div>

  <div class="robot__foot">
    <div class="robot__state">
      <h2 class="robot__title">État du robot</h2>
      <button type="button" class="robot__link" onclick={onOpenRobot}>
        <span class="robot__dot" class:robot__dot--on={status.connected} aria-hidden="true"></span>
        {status.connected ? 'En ligne' : 'Hors ligne'}
      </button>
    </div>

    <div class="robot__gauges">
      {#if posture}
        <span class="gauge" title="Posture demandée au robot">
          <Icon name="balance" size={21} />
          <span class="gauge__value">{posture}</span>
        </span>
      {/if}
      <span class="gauge" title="Batterie">
        <Icon name="battery" size={21} />
        <span class="gauge__value">{battery}</span>
      </span>
      <span
        class="gauge"
        class:gauge--off={!status.connected}
        title={status.connected ? 'Robot connecté' : 'Robot non connecté'}
      >
        <Icon name="wifi" size={21} />
      </span>
    </div>
  </div>
</aside>

<style>
  .robot {
    display: flex;
    flex-direction: column;
    min-width: 0;
    min-height: 0;
    padding: 10px;
    background: #242731;
    border: 1px solid #2f3441;
    border-radius: 22px;
    box-shadow:
      inset 0 1px 0 rgb(255 255 255 / 4%),
      0 18px 40px rgb(0 0 0 / 25%);
  }

  .scene {
    position: relative;
    flex: 1;
    min-height: 260px;
    border-radius: 16px;
    overflow: hidden;
    background: #0d1016;
    box-shadow: inset 0 0 0 1px rgb(0 0 0 / 20%);
  }

  .scene:fullscreen {
    border-radius: 0;
  }

  /* La scène lidar reste montée : le modèle n'est chargé qu'une fois, et
     les cubes apparaissent quand le bouton lidar est actif. */
  .scene__robot {
    position: absolute;
    inset: 0;
  }

  .scene__camera {
    position: absolute;
    inset: 0;
    z-index: 1;
    display: block;
    width: 100%;
    height: 100%;
    object-fit: cover;
    background: #10131a;
  }

  .scene__absent {
    position: absolute;
    inset: 0;
    z-index: 2;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 12px;
    padding: 24px;
    text-align: center;
    color: #9aa3b5;
    background: #1b1f28;
  }

  .scene__absent p {
    margin: 0;
    font-size: 14px;
    max-width: 24ch;
  }

  .scene__note {
    position: absolute;
    left: 14px;
    right: 14px;
    bottom: 56px;
    z-index: 2;
    margin: 0;
    padding: 10px 14px;
    border-radius: 12px;
    background: rgb(22 26 33 / 78%);
    border: 1px solid rgb(255 255 255 / 12%);
    color: #e9eef7;
    font-size: 13px;
    text-align: center;
    backdrop-filter: blur(8px);
  }

  .scene__btn {
    position: absolute;
    top: 14px;
    z-index: 3;
    display: grid;
    place-items: center;
    width: 42px;
    height: 42px;
    border: 1px solid rgb(255 255 255 / 18%);
    border-radius: 13px;
    background: rgb(22 26 33 / 55%);
    color: #eaf0f8;
    backdrop-filter: blur(8px);
    cursor: pointer;
    transition:
      background 0.15s ease,
      transform 0.12s ease;
  }

  .scene__btn:hover {
    background: rgb(22 26 33 / 78%);
    transform: translateY(-1px);
  }

  .scene__btn:focus-visible {
    outline: 2px solid #fff;
    outline-offset: 2px;
  }

  .scene__btn--left {
    left: 14px;
  }

  .scene__btn--right {
    right: 14px;
  }

  /* Bouton actif : la caméra ou le lidar est à l'écran. */
  .scene__btn--on {
    background: rgb(63 191 114 / 80%);
    border-color: rgb(143 228 168 / 60%);
    color: #06210f;
  }

  .scene__badge {
    position: absolute;
    left: 14px;
    bottom: 14px;
    z-index: 3;
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 7px 13px;
    border-radius: 999px;
    background: rgb(22 26 33 / 62%);
    border: 1px solid rgb(255 255 255 / 14%);
    color: #e9eef7;
    font-size: 12.5px;
    font-weight: 650;
    backdrop-filter: blur(8px);
  }

  .scene__dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: #f0b34a;
    box-shadow: 0 0 10px rgb(240 179 74 / 80%);
  }

  .scene__badge--on .scene__dot {
    background: #55d98a;
    box-shadow: 0 0 10px rgb(85 217 138 / 85%);
  }

  .robot__foot {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 14px 8px 4px;
  }

  .robot__state {
    min-width: 0;
  }

  .robot__title {
    margin: 0;
    font-size: 17px;
    font-weight: 700;
    letter-spacing: -0.01em;
    color: #e7ecf6;
  }

  .robot__link {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    margin-top: 4px;
    padding: 0;
    border: 0;
    background: transparent;
    font: inherit;
    font-size: 14px;
    font-weight: 600;
    color: #a7b0c2;
    cursor: pointer;
  }

  .robot__link:hover {
    color: #e7ecf6;
    text-decoration: underline;
  }

  .robot__link:focus-visible {
    outline: 2px solid #9fc4ec;
    outline-offset: 3px;
    border-radius: 6px;
  }

  .robot__dot {
    width: 10px;
    height: 10px;
    border-radius: 50%;
    background: #6b7385;
  }

  .robot__dot--on {
    background: #4fd98a;
    box-shadow: 0 0 10px rgb(79 217 138 / 80%);
    animation: pulse-dot 2s ease-in-out infinite;
  }

  @keyframes pulse-dot {
    0%,
    100% {
      opacity: 1;
    }
    50% {
      opacity: 0.55;
    }
  }

  .robot__gauges {
    display: flex;
    align-items: center;
    gap: 14px;
    margin-left: auto;
    color: #b9c2d3;
  }

  .gauge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: 14px;
    font-weight: 650;
  }

  .gauge--off {
    color: #6b7385;
  }

  .gauge__value {
    min-width: 3.2ch;
    text-align: right;
    font-variant-numeric: tabular-nums;
  }

  @media (prefers-reduced-motion: reduce) {
    .robot__dot--on {
      animation: none;
    }
  }
</style>
