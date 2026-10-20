<script lang="ts">
  /**
   * Vue « robot » : la scène, l'état réel et les raccourcis.
   *
   * La scène est une illustration : le robot n'envoie pas de flux vidéo dans
   * cette version. Les valeurs affichées (batterie, position) viennent, elles,
   * du service — et restent « — » quand aucune mesure n'existe.
   *
   * Le dessin est composé en portrait : la colonne de droite est haute et
   * étroite. Un cadrage paysage y perdrait le chien ; ici, un recadrage
   * moderé retire des arbres, jamais le robot.
   */
  import Icon from './Icon.svelte';
  import type { RobotStatus } from '../../lib/api/client';

  interface Props {
    status: RobotStatus;
    onRefresh: () => void;
    onOpenRobot: () => void;
  }

  let { status, onRefresh, onOpenRobot }: Props = $props();

  let sceneEl = $state<HTMLDivElement | undefined>();

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

  async function toggleFullscreen(): Promise<void> {
    if (!sceneEl) return;
    try {
      if (document.fullscreenElement) await document.exitFullscreen();
      else await sceneEl.requestFullscreen();
    } catch {
      // Le navigateur peut refuser (iframe, politique locale) : on n'insiste pas.
    }
  }
</script>

<aside class="robot" aria-label="État du robot">
  <div class="scene" bind:this={sceneEl}>
    <svg
      class="scene__art"
      viewBox="0 0 440 620"
      preserveAspectRatio="xMidYMid slice"
      role="img"
      aria-label="Illustration du robot Go2 dans un parc"
    >
      <defs>
        <linearGradient id="ciel" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="#cfe9f7" />
          <stop offset="100%" stop-color="#eaf6e3" />
        </linearGradient>
        <linearGradient id="herbe" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="#8ac868" />
          <stop offset="100%" stop-color="#4f9139" />
        </linearGradient>
        <linearGradient id="corps" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="#5a6170" />
          <stop offset="55%" stop-color="#3d4350" />
          <stop offset="100%" stop-color="#2b303a" />
        </linearGradient>
        <radialGradient id="ombre" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stop-color="#2f5c2a" stop-opacity="0.45" />
          <stop offset="100%" stop-color="#2f5c2a" stop-opacity="0" />
        </radialGradient>
      </defs>

      <rect width="440" height="620" fill="url(#ciel)" />
      <path d="M0 168 Q 110 132 220 158 T 440 150 V620 H0 Z" fill="url(#herbe)" />

      <!-- Arbres -->
      <g>
        <rect x="34" y="150" width="13" height="86" rx="6" fill="#8a5a35" />
        <circle cx="40" cy="138" r="44" fill="#4f9a4a" />
        <circle cx="10" cy="162" r="27" fill="#5fae57" />
        <circle cx="72" cy="164" r="29" fill="#6cbb62" />
      </g>
      <g>
        <rect x="392" y="158" width="12" height="76" rx="6" fill="#8a5a35" />
        <circle cx="398" cy="148" r="36" fill="#4f9a4a" />
        <circle cx="428" cy="170" r="25" fill="#6cbb62" />
        <circle cx="370" cy="172" r="23" fill="#5fae57" />
      </g>

      <!-- Barrière -->
      <g stroke="#b9814c" stroke-linecap="round">
        <path d="M14 250 H 426" stroke-width="9" />
        <path d="M14 286 H 426" stroke-width="9" />
        <g stroke="#a06b3c" stroke-width="11">
          <path d="M54 230 V 320" />
          <path d="M146 230 V 320" />
          <path d="M238 230 V 320" />
          <path d="M330 230 V 320" />
          <path d="M410 230 V 320" />
        </g>
      </g>

      <ellipse cx="250" cy="512" rx="152" ry="24" fill="url(#ombre)" />

      <g class="dog">
        <!-- Pattes -->
        <g
          fill="none"
          stroke="#343945"
          stroke-width="11"
          stroke-linecap="round"
          stroke-linejoin="round"
        >
          <path d="M178 398 L166 454 L171 500" />
          <path d="M212 398 L224 454 L220 500" />
          <path d="M302 398 L314 454 L310 500" />
          <path d="M336 398 L350 452 L346 500" />
        </g>
        <g fill="#4d5464">
          <circle cx="166" cy="454" r="6.5" />
          <circle cx="224" cy="454" r="6.5" />
          <circle cx="314" cy="454" r="6.5" />
          <circle cx="350" cy="452" r="6.5" />
        </g>
        <g fill="#23262f">
          <rect x="162" y="494" width="17" height="13" rx="5" />
          <rect x="212" y="494" width="17" height="13" rx="5" />
          <rect x="302" y="494" width="17" height="13" rx="5" />
          <rect x="338" y="494" width="17" height="13" rx="5" />
        </g>

        <!-- Corps -->
        <rect
          x="140"
          y="338"
          width="222"
          height="72"
          rx="33"
          fill="url(#corps)"
          stroke="#20242c"
          stroke-width="2"
        />
        <rect x="164" y="352" width="176" height="9" rx="4.5" fill="#767f92" opacity="0.5" />
        <path
          d="M168 392 H 336"
          stroke="#5fd0ff"
          stroke-width="4"
          stroke-linecap="round"
          opacity="0.9"
        />
        <rect x="226" y="362" width="50" height="17" rx="8.5" fill="#2f74b8" opacity="0.9" />
        <circle cx="251" cy="370.5" r="3.8" fill="#8fe4ff" />

        <!-- Tête -->
        <rect
          x="104"
          y="344"
          width="98"
          height="62"
          rx="25"
          fill="url(#corps)"
          stroke="#20242c"
          stroke-width="2"
        />
        <rect x="88" y="370" width="42" height="32" rx="15" fill="#2f343e" />
        <rect x="100" y="382" width="17" height="7" rx="3.5" fill="#14171d" />
        <rect
          x="128"
          y="322"
          width="25"
          height="27"
          rx="10.5"
          fill="#2f343e"
          transform="rotate(-10 140 335)"
        />
        <rect
          x="170"
          y="322"
          width="25"
          height="27"
          rx="10.5"
          fill="#2f343e"
          transform="rotate(12 182 335)"
        />
        <circle cx="129" cy="362" r="7.5" fill="#7ce7ff" />
        <circle cx="129" cy="362" r="2.8" fill="#eaffff" />
        <circle cx="196" cy="360" r="3.6" fill="#5fd0ff" opacity="0.8" />
      </g>
    </svg>

    <div class="scene__glow" aria-hidden="true"></div>

    <button
      type="button"
      class="scene__btn scene__btn--left"
      aria-label="Actualiser l’état du robot"
      title="Actualiser l’état"
      onclick={onRefresh}
    >
      <Icon name="refresh" size={18} />
    </button>

    <button
      type="button"
      class="scene__btn scene__btn--right"
      aria-label="Afficher la scène en plein écran"
      title="Plein écran"
      onclick={toggleFullscreen}
    >
      <Icon name="expand" size={18} />
    </button>

    <span class="scene__badge" class:scene__badge--on={status.connected}>
      <span class="scene__dot" aria-hidden="true"></span>
      {status.mode === 'real' ? 'Robot réel' : 'Simulation'}
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
    background: #6cae55;
    box-shadow: inset 0 0 0 1px rgb(0 0 0 / 20%);
  }

  .scene:fullscreen {
    border-radius: 0;
  }

  .scene__art {
    display: block;
    width: 100%;
    height: 100%;
  }

  .scene__glow {
    position: absolute;
    inset: 0;
    pointer-events: none;
    background:
      linear-gradient(180deg, rgb(255 255 255 / 10%) 0%, transparent 35%),
      radial-gradient(120% 80% at 50% 120%, rgb(20 60 20 / 35%) 0%, transparent 60%);
  }

  .scene__btn {
    position: absolute;
    top: 14px;
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

  .scene__badge {
    position: absolute;
    left: 14px;
    bottom: 14px;
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

  .dog {
    transform-origin: 50% 100%;
    animation: idle 3.6s ease-in-out infinite;
  }

  @keyframes idle {
    0%,
    100% {
      transform: translateY(0);
    }
    50% {
      transform: translateY(-3px);
    }
  }

  @media (prefers-reduced-motion: reduce) {
    .dog,
    .robot__dot--on {
      animation: none;
    }
  }
</style>
