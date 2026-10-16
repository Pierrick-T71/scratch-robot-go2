import { describe, it, expect, beforeEach } from 'vitest';
import {
  loadPreferences,
  savePreferences,
  DEFAULT_PREFERENCES,
  SETTING_DESCRIPTORS,
} from '../src/lib/robot/settings';
import { validateCommands } from '../src/lib/robot/validate';

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

describe('réglages — effet sur la validation', () => {
  it('applique la vitesse abaissée du service', () => {
    // 50 cm à 0.1 m/s : la durée change, donc la limite est bien lue.
    const fast = validateCommands([{ kind: 'move_forward', distanceCm: 50 }]);
    const slow = validateCommands([{ kind: 'move_forward', distanceCm: 50 }], undefined, {
      max_linear_speed: 0.1,
    });
    expect(fast.summary.estimatedSeconds).toBeLessThan(slow.summary.estimatedSeconds);
  });

  it('refuse un programme dépassant la nouvelle limite de pas', () => {
    const steps = Array.from({ length: 60 }, () => ({ kind: 'stop' as const }));
    // 60 pas < 500 par défaut : accepté.
    expect(validateCommands(steps).valid).toBe(true);
    // Avec le service réglé à 50 pas maximum : refusé.
    expect(validateCommands(steps, undefined, { max_total_steps: 50 }).valid).toBe(false);
  });

  it('refuse une distance dépassant la limite abaissée', () => {
    const program = [{ kind: 'move_forward', distanceCm: 150 }];
    expect(validateCommands(program).valid).toBe(true);
    // Service réglé à 100 cm par déplacement.
    expect(
      validateCommands(program, undefined, { max_distance_per_step_cm: 100 }).valid,
    ).toBe(false);
  });

  it('ignore une valeur de réglage aberrante', () => {
    // Le service ne devrait jamais envoyer ça, mais on ne doit pas planter.
    const program = [{ kind: 'move_forward', distanceCm: 50 }];
    expect(
      validateCommands(program, undefined, { max_distance_per_step_cm: NaN }).valid,
    ).toBe(true);
    expect(
      validateCommands(program, undefined, { max_distance_per_step_cm: Infinity }).valid,
    ).toBe(true);
  });

  it('utilise le fichier partagé pour les champs non transmis', () => {
    const program = [{ kind: 'wait', seconds: 2 }];
    // Seul un réglage transmis est appliqué, pas tous.
    expect(validateCommands(program, undefined, { max_linear_speed: 0.1 }).valid).toBe(true);
  });
});