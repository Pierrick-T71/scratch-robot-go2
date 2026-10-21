<script lang="ts">
  /**
   * Jeu d'icônes de « Go2 Play ».
   *
   * Un seul composant, un trait homogène : les icônes de l'interface sont
   * dessinées (pas d'émojis), pour que le rendu reste identique partout.
   * Les icônes de blocs sont pleines, les icônes d'action sont au trait.
   */
  interface Props {
    name: string;
    size?: number;
  }

  let { name, size = 24 }: Props = $props();
</script>

<svg
  class="icon"
  width={size}
  height={size}
  viewBox="0 0 24 24"
  fill="none"
  stroke="currentColor"
  stroke-width="1.9"
  stroke-linecap="round"
  stroke-linejoin="round"
  aria-hidden="true"
  focusable="false"
>
  {#if name === 'arrow-right'}
    <path d="M4 12h14M12 6l6 6-6 6" />
  {:else if name === 'arrow-left'}
    <path d="M20 12H6M12 6l-6 6 6 6" />
  {:else if name === 'turn-left'}
    <path d="M8 5 3 10l5 5" />
    <path d="M3 10h9a6 6 0 0 1 6 6v3" />
  {:else if name === 'turn-right'}
    <path d="M16 5l5 5-5 5" />
    <path d="M21 10h-9a6 6 0 0 0-6 6v3" />
  {:else if name === 'sit'}
    <circle cx="9" cy="5" r="2.4" />
    <path d="M9 7.4V13h7v6" />
    <path d="M9 13l-2 6" />
    <path d="M6 18h6" />
  {:else if name === 'stand'}
    <circle cx="12" cy="4.6" r="2.4" />
    <path d="M12 7v7" />
    <path d="M12 14l-3 7M12 14l3 7" />
    <path d="M12 9.5 8.4 12M12 9.5l3.6 2.5" />
  {:else if name === 'balance'}
    <path d="M12 4v16" />
    <path d="M4 7h16" />
    <path d="M4 7l-2 4h4zM20 7l-2 4h4z" />
    <path d="M7 20h10" />
  {:else if name === 'play'}
    <path d="M8 5.2v13.6L19 12z" fill="currentColor" stroke="none" />
  {:else if name === 'stop'}
    <rect x="6" y="6" width="12" height="12" rx="2.4" fill="currentColor" stroke="none" />
  {:else if name === 'save'}
    <path d="M5 4h11l3 3v13H5z" />
    <path d="M8 4v6h7V4" />
    <path d="M8 20v-6h8v6" />
  {:else if name === 'flag'}
    <path d="M6 3v18" />
    <path d="M6 4h11l-2.6 3.6L17 11H6z" fill="currentColor" stroke="none" />
  {:else if name === 'battery'}
    <rect x="2.5" y="8" width="16" height="8" rx="2.2" />
    <path d="M21.5 10.6v2.8" />
    <rect x="5" y="10.4" width="8" height="3.2" rx="1" fill="currentColor" stroke="none" />
  {:else if name === 'wifi'}
    <path d="M2.8 9.2a14 14 0 0 1 18.4 0" />
    <path d="M6 12.6a9 9 0 0 1 12 0" />
    <path d="M9.2 16a4.2 4.2 0 0 1 5.6 0" />
    <circle cx="12" cy="19" r="1.4" fill="currentColor" stroke="none" />
  {:else if name === 'refresh'}
    <path d="M20 12a8 8 0 1 1-2.4-5.7" />
    <path d="M20 4v5h-5" />
  {:else if name === 'expand'}
    <path d="M4 9V4h5M15 4h5v5M20 15v5h-5M9 20H4v-5" />
  {:else if name === 'trash'}
    <path d="M4 7h16" />
    <path d="M9 7V4h6v3" />
    <path d="M6 7l1 13h10l1-13" />
    <path d="M10 11v5M14 11v5" />
  {:else if name === 'settings'}
    <path d="M4 7h9M17 7h3M4 17h3M11 17h9" />
    <circle cx="15" cy="7" r="2.2" />
    <circle cx="9" cy="17" r="2.2" />
  {:else if name === 'help'}
    <circle cx="12" cy="12" r="9" />
    <path d="M9.6 9.2a2.6 2.6 0 1 1 3.6 2.4c-.8.4-1.2 1-1.2 1.9v.3" />
    <circle cx="12" cy="17" r="0.9" fill="currentColor" stroke="none" />
  {:else if name === 'radar'}
    <circle cx="12" cy="12" r="8.5" />
    <circle cx="12" cy="12" r="4.5" />
    <path d="M12 12 19 5" />
  {:else if name === 'arrow-up'}
    <path d="M12 20V5M12 5 6 11M12 5l6 6" />
  {:else if name === 'moon'}
    <path
      d="M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5z"
      fill="currentColor"
      stroke="none"
    />
  {:else if name === 'heart'}
    <path
      d="M12 20.3 4.6 13a4.6 4.6 0 0 1 6.5-6.5l.9.9.9-.9A4.6 4.6 0 0 1 19.4 13z"
      fill="currentColor"
      stroke="none"
    />
  {:else if name === 'wave'}
    <path
      d="M8.1 12.3V6.4a1.5 1.5 0 0 1 3 0v4.7m0 .5V4.8a1.5 1.5 0 0 1 3 0v6.8m0 .4V6.7a1.5 1.5 0 0 1 3 0v7.1c0 4-2.5 6.6-6.2 6.6-3.1 0-5.2-2-5.8-4.9l-.7-3.2a1.5 1.5 0 0 1 2.8-1.2l1 2.1"
    />
    <path d="M3 4.8c1.2.4 2 1.2 2.5 2.4M2.4 8.2c.8.4 1.4 1 1.8 1.9" />
  {:else if name === 'stretch'}
    <circle cx="12" cy="4.2" r="2.1" />
    <path d="M12 6.3v6.3" />
    <path d="M12 8.2 6.8 4.6M12 8.2l5.2-3.6" />
    <path d="M12 12.6 9 20M12 12.6l3 7.4" />
    <path d="M6.5 20h4M13.5 20h4" />
  {:else if name === 'paw'}    <ellipse cx="7" cy="8.5" rx="2.2" ry="2.8" fill="currentColor" stroke="none" />
    <ellipse cx="12" cy="6.6" rx="2.2" ry="2.9" fill="currentColor" stroke="none" />
    <ellipse cx="17" cy="8.5" rx="2.2" ry="2.8" fill="currentColor" stroke="none" />
    <ellipse cx="19.4" cy="13.4" rx="1.9" ry="2.4" fill="currentColor" stroke="none" />
    <path
      d="M12 11.4c3.2 0 6.2 2.5 6.2 5.2 0 2-1.7 3.2-3.7 2.6-1.6-.5-3.4-.5-5 0-2 .6-3.7-.6-3.7-2.6 0-2.7 3-5.2 6.2-5.2z"
      fill="currentColor"
      stroke="none"
    />
  {:else if name === 'star'}
    <path
      d="M12 2.8l2.7 5.7 6.2.8-4.6 4.3 1.2 6.1L12 16.8 6.5 19.7l1.2-6.1L3.1 9.3l6.2-.8z"
      fill="currentColor"
      stroke="none"
    />
  {:else if name === 'sparkle'}
    <path
      d="M12 2.4l1.9 6.9 6.9 1.9-6.9 1.9-1.9 6.9-1.9-6.9L4.2 11.2l6.9-1.9z"
      fill="currentColor"
      stroke="none"
    />
  {:else if name === 'camera'}
    <path d="M4 8h3l2-2h6l2 2h3v11H4z" />
    <circle cx="12" cy="13" r="3.4" />
  {:else if name === 'hand'}
    <path
      d="M8.2 12.4V6.3a1.55 1.55 0 0 1 3.1 0v4.9m0 .6V4.9a1.55 1.55 0 0 1 3.1 0v6.9m0 .4V6.6a1.55 1.55 0 0 1 3.1 0v7.2c0 4.1-2.6 6.8-6.4 6.8-3.2 0-5.4-2-6-5.1l-.7-3.3a1.55 1.55 0 0 1 2.8-1.2l1 2.2"
    />
  {:else if name === 'home'}
    <path d="M4 11l8-7 8 7v9h-6v-6h-4v6H4z" />
  {:else}
    <circle cx="12" cy="12" r="8" />
  {/if}
</svg>

<style>
  .icon {
    display: block;
    flex: none;
  }
</style>
