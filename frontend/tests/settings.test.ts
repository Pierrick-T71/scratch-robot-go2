import { describe, it, expect, beforeEach } from 'vitest';
import {
  loadPreferences,
  savePreferences,
  DEFAULT_PREFERENCES,
  SETTING_DESCRIPTORS,
} from '../src/lib/robot/settings';

class MemoryStorage {
  private data = new Map<string, string>();
  getItem(key: string): string | null {
    return this.data.get(key) ?? null;
  }
  setItem(key: string, value: string): void {
    this.data.set(key, value);
  }
  clear(): void {
    this.data.clear();
  }
}

beforeEach(() => {
  Object.defineProperty(globalThis, 'localStorage', {
    value: new MemoryStorage(),
    configurable: true,
    writable: true,
  });
});

describe('réglages — descripteurs', () => {
  it('décrit chaque réglage modifiable du service', () => {
    for (const d of SETTING_DESCRIPTORS) {
      expect(d.field).toBeTruthy();
      expect(d.label).toBeTruthy();
      expect(d.help).toBeTruthy();
      expect(d.step).toBeGreaterThan(0);
    }
  });

  it('n’a aucun doublon de champ', () => {
    const fields = SETTING_DESCRIPTORS.map((d) => d.field);
    expect(new Set(fields).size).toBe(fields.length);
  });

  it('couvre tous les réglages exposés par l’API', () => {
    // Les 10 champs doivent être présentables dans le panneau.
    expect(SETTING_DESCRIPTORS).toHaveLength(10);
  });
});

describe('réglages — préférences locales', () => {
  it('renvoie les valeurs par défaut si rien n’est stocké', () => {
    expect(loadPreferences()).toEqual(DEFAULT_PREFERENCES);
  });

  it('enregistre puis relit', () => {
    savePreferences({ serviceUrl: 'http://192.168.1.50:8765', theme: 'sombre' });
    expect(loadPreferences()).toEqual({
      serviceUrl: 'http://192.168.1.50:8765',
      theme: 'sombre',
    });
  });

  it('refuse une URL non http(s)', () => {
    // Un protocole dangereux ne doit jamais être stockable.
    expect(() =>
      savePreferences({ serviceUrl: 'file:///etc/passwd', theme: 'clair' }),
    ).toThrow();
    expect(() =>
      savePreferences({ serviceUrl: 'javascript:alert(1)', theme: 'clair' }),
    ).toThrow();
  });

  it('ignore une URL invalide au chargement', () => {
    globalThis.localStorage.setItem(
      'go2-scratch.prefs.v1',
      JSON.stringify({ serviceUrl: 'pas-une-url', theme: 'sombre' }),
    );
    // Repli sur la valeur par défaut, mais le thème valide est conservé.
    const prefs = loadPreferences();
    expect(prefs.serviceUrl).toBe(DEFAULT_PREFERENCES.serviceUrl);
    expect(prefs.theme).toBe('sombre');
  });

  it('ignore un thème inconnu', () => {
    globalThis.localStorage.setItem(
      'go2-scratch.prefs.v1',
      JSON.stringify({ serviceUrl: 'http://127.0.0.1:8765', theme: 'fluo' }),
    );
    expect(loadPreferences().theme).toBe('clair');
  });

  it('survit à un stockage corrompu', () => {
    globalThis.localStorage.setItem('go2-scratch.prefs.v1', '{ pas du json');
    expect(loadPreferences()).toEqual(DEFAULT_PREFERENCES);
  });
});

// L'effet des reglages sur la VALIDATION est verifie dans
// tests/validate.test.ts : il concerne le modele de programme, pas les
// reglages eux-memes.
