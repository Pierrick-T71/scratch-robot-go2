<script lang="ts">
  /**
   * Panneau de configuration.
   *
   * Deux sections :
   *  - « Réglages du robot » : limites de mouvement, résérvées à un adulte,
   *    réellement appliquées côté service (donc contraignantes).
   *  - « Préférences » : adresse du service et thème, purement locales.
   *
   * Aucune valeur n'est calculée ici : les bornes viennent du service.
   */
  import { app } from '../lib/stores/app.svelte';
  import {
    SETTING_DESCRIPTORS,
    loadPreferences,
    savePreferences,
    DEFAULT_PREFERENCES,
    type Preferences,
    type SettingsValues,
  } from '../lib/robot/settings';

  interface Props {
    onClose: () => void;
  }

  let { onClose }: Props = $props();

  const CONFIRM_WORD = 'RÉGLAGES';

  let prefs = $state<Preferences>(loadPreferences());
  let draft = $state<SettingsValues>({});
  let confirmWord = $state('');
  let saving = $state(false);
  let prefsMessage = $state<string | null>(null);

  /** Le service est la source des bornes : rien n'est proposé avant sa réponse. */
  const bounds = $derived(app.settings?.bounds ?? {});
  const canEdit = $derived(app.settings !== null && !app.isBusy);

  const confirmOk = $derived(confirmWord.trim().toUpperCase() === CONFIRM_WORD);

  /** Valeur courante affichée : brouillon si modifié, sinon valeur du service. */
  function valueOf(field: string): number | undefined {
    const edited = draft[field];
    if (edited !== undefined) return edited;
    return app.settings?.values[field];
  }

  function boundsOf(field: string): { min: number; max: number } | undefined {
    return bounds[field];
  }

  function isModified(field: string): boolean {
    return draft[field] !== undefined && draft[field] !== app.settings?.values[field];
  }

  function formatValue(value: number, step: number): string {
    const decimals = step < 1 ? 2 : 0;
    return value.toFixed(decimals);
  }

  async function saveRobotSettings(): Promise<void> {
    if (!canEdit || !confirmOk || saving) return;
    saving = true;
    const ok = await app.saveSettings({ ...draft });
    saving = false;
    if (ok) {
      draft = {};
      confirmWord = '';
    }
  }

  function resetDraft(): void {
    draft = {};
    confirmWord = '';
  }

  function resetToDefaults(): void {
    void savePreferences({ ...DEFAULT_PREFERENCES });
    prefs = { ...DEFAULT_PREFERENCES };
    prefsMessage = 'Préférences revenues par défaut.';
  }

  function applyPrefs(): void {
    try {
      savePreferences(prefs);
      prefsMessage = 'Préférences enregistrées. Recharge la page pour les appliquer.';
    } catch (error) {
      prefsMessage = error instanceof Error ? error.message : 'Réglages refusés.';
    }
  }
</script>

<div
  class="modal-backdrop"
  role="presentation"
  onclick={(e) => e.target === e.currentTarget && onClose()}
>
  <div class="modal modal--wide" role="dialog" aria-modal="true" aria-labelledby="settings-title">
    <header class="modal__header">
      <span class="modal__icon" aria-hidden="true">⚙️</span>
      <div>
        <h2 class="modal__title" id="settings-title">Configuration</h2>
        <p class="modal__subtitle">Réglages du robot et préférences de l’application</p>
      </div>
      <button type="button" class="btn btn--ghost btn--sm modal__close" onclick={onClose}>
        Fermer
      </button>
    </header>

    <div class="modal__body">
      <!-- ============================ REGLAGES DU ROBOT ============================ -->
      <section class="section">
        <h3 class="section__title">
          Réglages du robot
          <span class="section__badge section__badge--adult">Adulte</span>
        </h3>

        <p class="section__intro">
          Ces limites déterminent ce que le robot est autorisé à faire. Elles
          sont appliquées par le service, qui les contrôle à chaque
          programme.
        </p>

        {#if app.settings === null}
          <div class="message message--warn">
            <span class="message__icon" aria-hidden="true">⚠️</span>
            <span>
              Le service ne répond pas : les réglages ne sont pas disponibles.
              Démarre-le pour pouvoir les modifier.
            </span>
          </div>
        {:else if app.isBusy}
          <div class="message message--warn">
            <span class="message__icon" aria-hidden="true">⏳</span>
            <span>
              Un programme est en cours. Attends qu’il se termine pour modifier
              les réglages.
            </span>
          </div>
        {:else}
          <div class="settings__grid">
            {#each SETTING_DESCRIPTORS as descriptor (descriptor.field)}
              {@const bounds = boundsOf(descriptor.field)}
              {#if bounds}
                <label
                  class="setting"
                  class:setting--modified={isModified(descriptor.field)}
                >
                  <span class="setting__head">
                    <span class="setting__label">{descriptor.label}</span>
                    <span class="setting__value">
                      {formatValue(valueOf(descriptor.field) ?? bounds.min, descriptor.step)}
                      {descriptor.unit}
                    </span>
                  </span>
                  <input
                    class="setting__range"
                    type="range"
                    min={bounds.min}
                    max={bounds.max}
                    step={descriptor.step}
                    value={valueOf(descriptor.field) ?? bounds.min}
                    oninput={(e) => {
                      draft[descriptor.field] = Number(e.currentTarget.value);
                    }}
                  />
                  <span class="setting__bounds">
                    {formatValue(bounds.min, descriptor.step)} → {formatValue(bounds.max, descriptor.step)}
                    {descriptor.unit}
                  </span>
                  <span class="setting__help">{descriptor.help}</span>
                </label>
              {/if}
            {/each}
          </div>

          {#if Object.keys(draft).length > 0}
            <div class="settings__confirm">
              <p class="settings__confirm-text">
                Pour appliquer les modifications, écris <strong>{CONFIRM_WORD}</strong>
                en majuscules&nbsp;:
              </p>
              <div class="settings__confirm-row">
                <input
                  class="input grow"
                  type="text"
                  bind:value={confirmWord}
                  placeholder={CONFIRM_WORD}
                  autocomplete="off"
                />
                <button
                  type="button"
                  class="btn"
                  disabled={!confirmOk || saving}
                  onclick={saveRobotSettings}
                >
                  <span aria-hidden="true">💾</span> Appliquer
                </button>
                <button type="button" class="btn btn--ghost" onclick={resetDraft}>
                  Annuler
                </button>
              </div>
              <p class="muted">
                Les programmes déjà vérifiés seront à revérifier avec les
                nouvelles limites.
              </p>
            </div>
          {/if}
        {/if}
      </section>

      <!-- ============================ PREFERENCES ============================ -->
      <section class="section">
        <h3 class="section__title">Préférences</h3>
        <p class="section__intro">
          Ces réglages n’affectent pas la sécurité du robot. Ils sont gardés
          uniquement sur cet appareil.
        </p>

        <div class="settings__grid settings__grid--simple">
          <label class="setting">
            <span class="setting__label">Adresse du service robot</span>
            <input
              class="input"
              type="text"
              bind:value={prefs.serviceUrl}
              placeholder="http://127.0.0.1:8765"
            />
            <span class="setting__help">
              Par défaut <code>http://127.0.0.1:8765</code>. À changer seulement
              si le service tourne sur un autre poste du réseau local.
            </span>
          </label>

          <label class="setting">
            <span class="setting__label">Thème</span>
            <div class="theme-toggle">
              <button
                type="button"
                class="theme-toggle__btn"
                class:theme-toggle__btn--active={prefs.theme === 'clair'}
                onclick={() => (prefs = { ...prefs, theme: 'clair' })}
              >
                ☀️ Clair
              </button>
              <button
                type="button"
                class="theme-toggle__btn"
                class:theme-toggle__btn--active={prefs.theme === 'sombre'}
                onclick={() => (prefs = { ...prefs, theme: 'sombre' })}
              >
                🌙 Sombre
              </button>
            </div>
            <span class="setting__help">
              Le thème sombre est enregistré mais pas encore appliqué à
              l’interface.
            </span>
          </label>
        </div>

        <div class="settings__confirm-row">
          <button type="button" class="btn btn--ghost" onclick={applyPrefs}>
            <span aria-hidden="true">💾</span> Enregistrer les préférences
          </button>
          <button type="button" class="btn btn--ghost" onclick={resetToDefaults}>
            Valeurs par défaut
          </button>
        </div>

        {#if prefsMessage}
          <div class="message message--ok" role="status">
            <span class="message__icon" aria-hidden="true">✅</span>
            <span>{prefsMessage}</span>
          </div>
        {/if}
      </section>
    </div>
  </div>
</div>

<style>
  .modal--wide {
    width: min(880px, 100%);
  }

  .modal__icon {
    font-size: 28px;
    line-height: 1;
  }

  .modal__subtitle {
    margin: 2px 0 0;
    font-size: 13px;
    color: var(--ink-500);
    font-weight: 500;
  }

  .modal__close {
    margin-left: auto;
    flex: none;
  }

  .section + .section {
    margin-top: 8px;
    padding-top: 18px;
    border-top: 1px solid var(--line);
  }

  .section__title {
    display: flex;
    align-items: center;
    gap: 9px;
    margin: 0 0 4px;
    font-size: 16px;
    font-weight: 800;
    color: var(--ink-900);
  }

  .section__badge {
    padding: 3px 9px;
    border-radius: 999px;
    font-size: 11px;
    font-weight: 800;
    text-transform: uppercase;
    letter-spacing: 0.4px;
  }

  .section__badge--adult {
    background: var(--brand-100);
    color: var(--brand-600);
  }

  .section__intro {
    margin: 0 0 14px;
    font-size: 13.5px;
    color: var(--ink-500);
    max-width: 62ch;
  }

  .settings__grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
    gap: 12px;
  }

  .settings__grid--simple {
    grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  }

  .setting {
    display: flex;
    flex-direction: column;
    gap: 6px;
    padding: 12px 14px;
    border: 1px solid var(--line);
    border-radius: var(--radius-m);
    background: var(--surface-2);
    transition: border-color 0.15s ease, background 0.15s ease;
  }

  .setting--modified {
    border-color: var(--brand-500);
    background: var(--brand-100);
  }

  .setting__head {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 8px;
  }

  .setting__label {
    font-size: 13.5px;
    font-weight: 700;
    color: var(--ink-700);
  }

  .setting__value {
    font-size: 15px;
    font-weight: 800;
    color: var(--brand-600);
    font-variant-numeric: tabular-nums;
  }

  .setting__range {
    width: 100%;
    accent-color: var(--brand-500);
    cursor: pointer;
  }

  .setting__bounds {
    font-size: 11px;
    color: var(--ink-500);
    font-variant-numeric: tabular-nums;
  }

  .setting__help {
    font-size: 12px;
    line-height: 1.4;
    color: var(--ink-500);
  }

  .setting__help code {
    padding: 1px 5px;
    border-radius: 4px;
    background: var(--line);
    font-size: 11.5px;
  }

  .settings__confirm {
    display: flex;
    flex-direction: column;
    gap: 8px;
    margin-top: 16px;
    padding: 14px;
    border-radius: var(--radius-m);
    background: var(--brand-100);
    border: 1px solid #c9d8ff;
  }

  .settings__confirm-text {
    margin: 0;
    font-size: 13.5px;
    color: var(--ink-700);
  }

  .settings__confirm-row {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
    align-items: center;
    margin-top: 10px;
  }

  .theme-toggle {
    display: flex;
    gap: 4px;
    padding: 3px;
    border-radius: var(--radius-s);
    background: var(--line);
  }

  .theme-toggle__btn {
    flex: 1;
    padding: 7px 10px;
    border: none;
    border-radius: calc(var(--radius-s) - 2px);
    background: transparent;
    font-family: inherit;
    font-size: 13px;
    font-weight: 600;
    color: var(--ink-500);
    cursor: pointer;
    transition: background 0.15s ease, color 0.15s ease;
  }

  .theme-toggle__btn--active {
    background: var(--surface);
    color: var(--ink-900);
    box-shadow: var(--shadow-xs);
  }
</style>