/**
 * Forme, libellés et CONNEXIONS de chaque bloc.
 *
 * C'est la suite qui répond à la question « les blocs sont-ils correctement
 * dessinés et emboîtables ? ». Elle inspecte le RENDU et les CONNEXIONS, pas
 * seulement les champs : un bloc muet reste parfaitement constructible, et un
 * bloc troué se construit sans erreur.
 *
 * Trois régressions réelles ont été trouvées par ces tests :
 *
 *  1. Les textes de TÊTE avaient disparu lors d'un passage JSON → JavaScript :
 *     « Avancer de [50] cm » s'affichait « [50] cm ».
 *  2. `new FieldVariable('compteur')` lève une exception si la variable
 *     n'existe pas : sans la locale française, TOUS les blocs à menu
 *    dropdown plantaient.
 *  3. `FieldNumber.setPrecision()` remet la valeur à zéro ET neutralise le
 *     champ dans cette version de Blockly.
 */
import { describe, it, expect, beforeAll } from 'vitest';
import * as Blockly from 'blockly/core';
import 'blockly/blocks';
import {
  BLOCK_DEFINITIONS,
  CATEGORIES,
  CATEGORY_COLOURS,
  COMPILABLE_BLOCKS,
  CONDITION_CHOICES,
  DURATION_CHOICES,
  REPEAT_CHOICES,
  TURN_CHOICES,
  registerGo2Blocks,
  verifyBlockLabels,
} from '../src/lib/blockly/blocks';
import { buildToolbox } from '../src/lib/blockly/workspace';

beforeAll(() => registerGo2Blocks());

function block(type: string): Blockly.Block {
  return new Blockly.Workspace().newBlock(type);
}

/** Tous les textes qu'un bloc affiche. */
function renderedTexts(type: string): string[] {
  const texts: string[] = [];
  for (const field of block(type).getFields()) {
    const value = field.getValue();
    if (typeof value === 'string' && value.length > 0) texts.push(value);
  }
  return texts;
}

/**
 * Types d'entrée Blockly.
 *
 * ⚠️ `Blockly.InputType` n'est PAS exporté par `blockly/core` dans cette
 * version. Les valeurs sont stables depuis Blockly 3, mais on les nomme
 * explicitement plutôt que de laisser des nombres magiques dans les tests.
 */
const INPUT_VALUE = 1;
const INPUT_STATEMENT = 3;
const INPUT_DUMMY = 5;

/** Types de toutes les entrées d'un bloc. */
function inputTypes(type: string): string[] {
  return block(type).inputList.map((input) => `${input.name}:${input.type}`);
}

// ---------------------------------------------------------------------------
// Libellés
// ---------------------------------------------------------------------------

describe('libellés', () => {
  it('aucun bloc déclaré n’a de libellé vide', () => {
    expect(verifyBlockLabels()).toEqual([]);
  });

  it.each(BLOCK_DEFINITIONS.map((d) => d.type))('%s affiche au moins un texte', (type) => {
    const texts = renderedTexts(type);
    expect(texts.length, `le bloc « ${type} » n’affiche aucun texte : il est muet`)
      .toBeGreaterThan(0);
  });

  const EXPECTED: Array<[string, string]> = [
    ['go2_start', 'Quand je clique sur Démarrer'],
    ['go2_move_forward', 'Avancer pendant'],
    ['go2_move_backward', 'Reculer pendant'],
    ['go2_move_left', 'Aller à gauche pendant'],
    ['go2_move_right', 'Aller à droite pendant'],
    ['go2_turn_left', 'Tourner à gauche de'],
    ['go2_turn_right', 'Tourner à droite de'],
    ['go2_stop_move', 'Arrêter le robot'],
    ['go2_stand_up', 'Se mettre debout'],
    ['go2_sit_down', "S'asseoir"],
    ['go2_balance', 'Se stabiliser'],
    ['go2_wait', 'Attendre'],
    ['go2_repeat', 'Répéter'],
    ['go2_stop_program', 'Arrêter le programme'],
  ];

  it.each(EXPECTED)('%s affiche le texte « %s »', (type, expected) => {
    expect(renderedTexts(type).join(' '), `texte manquant pour « ${type} »`).toContain(
      expected,
    );
  });

  it('aucun texte technique n’apparaît dans un bloc destiné aux enfants', () => {
    // Le cahier des charges exclut « variable », « expression », « API »,
    // « vitesse linéaire » de l'interface enfant.
    const interdits = [
      'variable',
      'expression',
      'AST',
      'API',
      'vitesse linéaire',
      'm/s',
      'rad/s',
    ];
    for (const definition of BLOCK_DEFINITIONS) {
      const joined = renderedTexts(definition.type).join(' ');
      for (const mot of interdits) {
        expect(joined.toLowerCase(), `${definition.type} contient « ${mot} »`).not.toContain(
          mot.toLowerCase(),
        );
      }
    }
  });
});

// ---------------------------------------------------------------------------
// Aucun trou vide
// ---------------------------------------------------------------------------

describe('aucune entrée à remplir', () => {
  it.each(BLOCK_DEFINITIONS.map((d) => d.type))(
    '%s n’a AUCUNE entrée de valeur',
    (type) => {
      // Une entrée de valeur dessine un creux visible tant que rien n'y est
      // branché. C'est ce qui rendait l'espace troué.
      const values = block(type).inputList.filter((input) => input.type === INPUT_VALUE);
      expect(values.map((v) => v.name), `${type} a une encoche à remplir`).toEqual([]);
    },
  );

  it('aucun bloc n’a de sortie', () => {
    // Pas de bloc à valeur du tout : il n'y a donc aucune forme d'encoche
    // ronde à faire coïncider avec un emplacement.
    for (const definition of BLOCK_DEFINITIONS) {
      expect(block(definition.type).outputConnection, definition.type).toBeNull();
    }
  });

  it('les seuls types d’entrée sont des corps de blocs ou des menus', () => {
    const autorises = new Set<string>();
    for (const nom of [
      'LABEL',
      'LEAD',
      'UNIT',
      'HEAD',
      'THEN',
      'ELSE_HEAD',
      'DURATION',
      'ANGLE',
      'SECONDS',
      'COUNT',
      'CONDITION',
    ]) {
      autorises.add(`${nom}:${INPUT_DUMMY}`);
    }
    autorises.add(`DO:${INPUT_STATEMENT}`);
    autorises.add(`ELSE:${INPUT_STATEMENT}`);

    for (const definition of BLOCK_DEFINITIONS) {
      for (const entree of inputTypes(definition.type)) {
        expect(
          autorises.has(entree),
          `${definition.type} : entrée inattendue « ${entree} »`,
        ).toBe(true);
      }
    }
  });
});

// ---------------------------------------------------------------------------
// Connexions
// ---------------------------------------------------------------------------

describe('connexions', () => {
  it('les blocs simples s’enchaînent au-dessus et en dessous', () => {
    const simples = [
      'go2_move_forward',
      'go2_move_backward',
      'go2_move_left',
      'go2_move_right',
      'go2_turn_left',
      'go2_turn_right',
      'go2_stop_move',
      'go2_stand_up',
      'go2_sit_down',
      'go2_balance',
      'go2_wait',
    ];
    for (const type of simples) {
      const b = block(type);
      expect(b.previousConnection, `${type} sans encoche haute`).not.toBeNull();
      expect(b.nextConnection, `${type} sans encoche basse`).not.toBeNull();
    }
  });

  it('« Arrêter le robot » s’enchaîne comme les autres', () => {
    // La demande explicite concernait « Arrêter le robot » : il DOIT avoir
    // une encoche basse, sinon on ne peut pas lui accrocher la suite.
    const b = block('go2_stop_move');
    expect(b.previousConnection).not.toBeNull();
    expect(b.nextConnection).not.toBeNull();
  });

  it('« Arrêter le programme » est terminal : PAS d’encoche basse', () => {
    // Une encoche basse sous un bloc terminal promettrait une suite possible
    // alors que le programme s’arrête justement là.
    const b = block('go2_stop_program');
    expect(b.previousConnection).not.toBeNull();
    expect(b.nextConnection, 'une encoche basse mentirait ici').toBeNull();
  });

  it('« Quand je clique sur Démarrer » est un bloc de départ', () => {
    const b = block('go2_start');
    expect(b.previousConnection, 'un bloc de départ n’a pas d’encoche haute').toBeNull();
    expect(b.nextConnection).not.toBeNull();
  });

  it('« Répéter » a exactement un corps', () => {
    expect(inputTypes('go2_repeat')).toEqual([
      `HEAD:${INPUT_DUMMY}`,
      `DO:${INPUT_STATEMENT}`,
    ]);
  });

  it('l’en-tête d’un bloc à corps tient sur une seule ligne', () => {
    // Régression : avec une entrée par champ, `setInputsInline(false)`
    // empilait « Répéter », le menu et « fois » sur trois lignes distinctes.
    // Tout l'en-tête doit tenir dans UNE entrée factice nommée HEAD.
    for (const type of ['go2_repeat', 'go2_if', 'go2_if_else']) {
      const tetes = block(type)
        .inputList.filter((input) => input.name === 'HEAD')
        .map((input) => input.type);
      expect(tetes, `${type} doit avoir une entrée HEAD unique`).toEqual([INPUT_DUMMY]);
    }
    // « Si … alors » est bien sur une seule ligne.
    expect(renderedTexts('go2_if').join(' ')).toContain('Si');
    expect(renderedTexts('go2_if').join(' ')).toContain('alors');
  });

  it('« Si » a un corps, « Si … sinon » en a deux', () => {
    expect(inputTypes('go2_if')).toContain(`DO:${INPUT_STATEMENT}`);
    expect(inputTypes('go2_if')).not.toContain(`ELSE:${INPUT_STATEMENT}`);

    const avecSinon = inputTypes('go2_if_else');
    expect(avecSinon).toContain(`DO:${INPUT_STATEMENT}`);
    expect(avecSinon).toContain(`ELSE:${INPUT_STATEMENT}`);
  });

  it('les blocs s’emboîtent réellement', () => {
    const workspace = new Blockly.Workspace();
    const a = workspace.newBlock('go2_move_forward');
    const b = workspace.newBlock('go2_turn_left');
    const c = workspace.newBlock('go2_stop_move');
    expect(a.nextConnection?.connect(b.previousConnection)).toBeTruthy();
    expect(b.nextConnection?.connect(c.previousConnection)).toBeTruthy();
  });

  it('une boucle accepte un corps et se poursuit après', () => {
    const workspace = new Blockly.Workspace();
    const loop = workspace.newBlock('go2_repeat');
    const inside = workspace.newBlock('go2_wait');
    const after = workspace.newBlock('go2_stop_move');

    expect(loop.getInput('DO')!.connection!.connect(inside.previousConnection!)).toBeTruthy();
    expect(loop.nextConnection?.connect(after.previousConnection!)).toBeTruthy();
    // Le bloc Following est à l'intérieur, pas après la boucle.
    expect(inside.nextConnection?.targetBlock()).toBeNull();
  });

  it('les deux branches d’un « Si … sinon » acceptent chacune un bloc', () => {
    const workspace = new Blockly.Workspace();
    const branch = workspace.newBlock('go2_if_else');
    const alors = workspace.newBlock('go2_stand_up');
    const sinon = workspace.newBlock('go2_sit_down');

    expect(branch.getInput('DO')!.connection!.connect(alors.previousConnection!)).toBeTruthy();
    expect(branch.getInput('ELSE')!.connection!.connect(sinon.previousConnection!)).toBeTruthy();
  });

  it('« Arrêter le programme » accepte d’être accroché et rien après', () => {
    const workspace = new Blockly.Workspace();
    const move = workspace.newBlock('go2_move_forward');
    const stop = workspace.newBlock('go2_stop_program');
    expect(move.nextConnection?.connect(stop.previousConnection!)).toBeTruthy();
    // Impossible d'accrocher quoi que ce soit après.
    expect(stop.nextConnection).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Menus déroulants
// ---------------------------------------------------------------------------

describe('menus déroulants', () => {
  it.each([
    ['go2_move_forward', 'DURATION'],
    ['go2_move_backward', 'DURATION'],
    ['go2_move_left', 'DURATION'],
    ['go2_move_right', 'DURATION'],
    ['go2_turn_left', 'ANGLE'],
    ['go2_turn_right', 'ANGLE'],
    ['go2_wait', 'SECONDS'],
    ['go2_repeat', 'COUNT'],
    ['go2_if', 'CONDITION'],
    ['go2_if_else', 'CONDITION'],
  ])('%s propose un menu nommé %s', (type, field) => {
    const menu = block(type).getField(field);
    expect(menu, `${type}.${field} introuvable`).not.toBeNull();
    expect(menu).toBeInstanceOf(Blockly.FieldDropdown);
  });

  it('les durées proposées sont celles annoncées', () => {
    const menu = block('go2_move_forward').getField('DURATION') as Blockly.FieldDropdown;
    const valeurs = menu.getOptions().map((option) => option[1]);
    expect(valeurs).toEqual(DURATION_CHOICES.map(([, value]) => value));
  });

  it('les angles proposés sont ceux annoncés', () => {
    const menu = block('go2_turn_left').getField('ANGLE') as Blockly.FieldDropdown;
    expect(menu.getOptions().map((o) => o[1])).toEqual(
      TURN_CHOICES.map(([, value]) => value),
    );
  });

  it('les répétitions proposées sont celles annoncées', () => {
    const menu = block('go2_repeat').getField('COUNT') as Blockly.FieldDropdown;
    expect(menu.getOptions().map((o) => o[1])).toEqual(
      REPEAT_CHOICES.map(([, value]) => value),
    );
  });

  it('aucune condition sans mesure réelle n’est proposée', () => {
    // ⚠️ « si un obstacle est détecté » n'est PAS proposé : aucune mesure de
    // distance n'a été identifiée dans le SDK officiel.
    const menu = block('go2_if').getField('CONDITION') as Blockly.FieldDropdown;
    const valeurs = menu.getOptions().map((o) => o[1]);
    expect(valeurs).toEqual(CONDITION_CHOICES.map(([, value]) => value));
    expect(valeurs).not.toContain('obstacle_detected');
  });

  it('le choix par défaut est valide', () => {
    expect(block('go2_move_forward').getFieldValue('DURATION')).toBe('2');
    expect(block('go2_turn_left').getFieldValue('ANGLE')).toBe('90');
    expect(block('go2_repeat').getFieldValue('COUNT')).toBe('3');
    expect(block('go2_if').getFieldValue('CONDITION')).toBe('posture_stand');
  });

  it('un choix fait par l’enfant est conservé', () => {
    const b = block('go2_move_forward');
    b.setFieldValue('5', 'DURATION');
    expect(b.getFieldValue('DURATION')).toBe('5');

    b.setFieldValue('90', 'DURATION') as unknown as void;
    expect(['1', '2', '3', '5']).toContain(String(b.getFieldValue('DURATION')));
  });

  it('les libellés des menus sont lisibles en français', () => {
    const menu = block('go2_if').getField('CONDITION') as Blockly.FieldDropdown;
    const labels = menu.getOptions().map((option) => String(option[0]));
    expect(labels).toContain('le robot est debout');
    for (const label of labels) {
      expect(label).not.toMatch(/[A-Z]{3,}/); // pas de « API », « AST »…
    }
  });

  it('« Répéter » porte le mot « fois » sur le bloc, pas dans le menu', () => {
    // Blockly remplace le libellé d'une option par sa valeur quand le libellé
    // est purement numérique. Le mot est donc sur le bloc, et les deux
    // affichages se complètent au lieu de se contredire.
    const menu = block('go2_repeat').getField('COUNT') as Blockly.FieldDropdown;
    expect(menu.getOptions().map((o) => String(o[0]))).toEqual(['2', '3', '5', '10']);
    expect(renderedTexts('go2_repeat').join(' ')).toContain('fois');
  });
});

// ---------------------------------------------------------------------------
// Métadonnées
// ---------------------------------------------------------------------------

describe('métadonnées', () => {
  it('chaque catégorie a une couleur', () => {
    for (const category of CATEGORIES) {
      expect(CATEGORY_COLOURS[category.name], category.name).toBeTruthy();
    }
  });

  it('chaque bloc appartient à une catégorie déclarée', () => {
    const names = new Set(CATEGORIES.map((c) => c.name));
    for (const definition of BLOCK_DEFINITIONS) {
      expect(names.has(definition.category), definition.type).toBe(true);
    }
  });

  it('aucun bloc n’est dans deux catégories', () => {
    const types = BLOCK_DEFINITIONS.map((d) => d.type);
    expect(new Set(types).size).toBe(types.length);
  });

  it('les trois catégories demandées sont présentes', () => {
    // « Capteurs » n'existe pas : les deux conditions mesurables tiennent
    // dans le menu d'un bloc « Si ». Une catégorie entière pour deux entrées
    // serait décorative.
    expect(CATEGORIES.map((c) => c.name)).toEqual(['movement', 'actions', 'control']);
  });

  it('tous les blocs sont compilables', () => {
    for (const definition of BLOCK_DEFINITIONS) {
      expect(COMPILABLE_BLOCKS.has(definition.type), definition.type).toBe(true);
    }
  });

  it('aucun bloc n’est marqué non vérifié', () => {
    // Les blocs non vérifiés ont été RETIRÉS, pas désactivés : proposer
    // « Se coucher » sans confirmation SDK serait un bloc décoratif.
    for (const definition of BLOCK_DEFINITIONS) {
      expect(definition.verifiedForRealMode, definition.type).toBe(true);
    }
  });

  it('aucun bloc de variable n’est proposé à l’enfant', () => {
    // ⚠️ `blockly/blocks` enregistre les blocs de variables Standards de
    // Blockly (`variables_get`, `variables_set`…). Ils sont présents sur le
    // namespace mais ABSENTS de la palette : c'est la palette qui décide de ce
    // que l'enfant voit.
    const palette = Object.values(buildToolbox().contents)
      .flatMap((category) => category.contents)
      .map((entry) => (entry as { type: string }).type);

    expect(palette.length).toBeGreaterThan(0);
    for (const type of palette) {
      expect(type, `« ${type} » est un bloc de variable`).not.toMatch(/var/i);
    }
  });

  it('aucun bloc GO2 n’a de nom évoquant une variable', () => {
    for (const definition of BLOCK_DEFINITIONS) {
      expect(definition.type, definition.type).not.toMatch(/var/i);
    }
  });
});