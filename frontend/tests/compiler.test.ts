/**
 * Traduction de l'espace de travail en programme.
 *
 * Le programme de référence est celui du cahier des charges :
 *
 *     Quand je clique sur Démarrer
 *     Avancer pendant 2 secondes
 *     Tourner à gauche de 90°
 *     Avancer pendant 2 secondes
 *     Arrêter le robot
 *
 * Il doit fonctionner SANS qu'aucune variable ne soit créée.
 */
import { describe, it, expect, beforeAll } from 'vitest';
import * as Blockly from 'blockly/core';
import 'blockly/blocks';
import { registerGo2Blocks } from '../src/lib/blockly/blocks';
import { compileWorkspace } from '../src/lib/blockly/compiler';
import { countSteps, flattenForDisplay, type Statement } from '../src/lib/robot/program';

beforeAll(() => registerGo2Blocks());

function chain(workspace: Blockly.Workspace, ...types: string[]): void {
  const start = workspace.newBlock('go2_start');
  let previous = start;
  for (const type of types) {
    const block = workspace.newBlock(type);
    previous.nextConnection!.connect(block.previousConnection!);
    previous = block;
  }
}

function attach(workspace: Blockly.Workspace, ...blocks: Blockly.Block[]): void {
  const start = workspace.newBlock('go2_start');
  let previous = start;
  for (const block of blocks) {
    previous.nextConnection!.connect(block.previousConnection!);
    previous = block;
  }
}

function find(workspace: Blockly.Workspace, type: string): Blockly.Block {
  const block = workspace.getAllBlocks(false).find((b) => b.type === type);
  if (!block) throw new Error(`bloc « ${type} » introuvable`);
  return block;
}

function first(workspace: Blockly.Workspace): Statement {
  return compileWorkspace(workspace).program.statements[0]!;
}

const move = (seconds = 2) => ({
  kind: 'move',
  direction: 'forward',
  seconds,
  line: expect.any(Number),
});
const turn = (degrees = 90) => ({
  kind: 'turn',
  direction: 'left',
  degrees,
  line: expect.any(Number),
});

// ---------------------------------------------------------------------------

describe('programme de référence', () => {
  it('se construit sans créer de variable', () => {
    const workspace = new Blockly.Workspace();
    chain(workspace, 'go2_move_forward', 'go2_turn_left', 'go2_move_forward', 'go2_stop_move');

    const result = compileWorkspace(workspace);
    expect(result.hasStart).toBe(true);
    expect(result.issues).toEqual([]);
    expect(result.program.statements).toEqual([
      move(2),
      turn(90),
      move(2),
      { kind: 'stop_move', line: expect.any(Number) },
    ]);
  });

  it('donne exactement le programme annoncé', () => {
    const workspace = new Blockly.Workspace();
    chain(workspace, 'go2_move_forward', 'go2_turn_left', 'go2_move_forward', 'go2_stop_move');
    const { program } = compileWorkspace(workspace);

    // 2 s + 90° (~3,1 s) + 2 s ≈ 7,1 s de mouvement.
    expect(program.statements).toHaveLength(4);
    expect(program.statements[0]).toMatchObject({ kind: 'move', seconds: 2 });
    expect(program.statements[1]).toMatchObject({ kind: 'turn', degrees: 90 });
    expect(program.statements[3]).toMatchObject({ kind: 'stop_move' });
  });
});

describe('déplacements', () => {
  it.each([
    ['go2_move_forward', 'forward'],
    ['go2_move_backward', 'backward'],
    ['go2_move_left', 'left'],
    ['go2_move_right', 'right'],
  ])('%s devient un déplacement %s', (type, direction) => {
    const workspace = new Blockly.Workspace();
    chain(workspace, type);
    expect(first(workspace)).toMatchObject({ kind: 'move', direction });
  });

  it('la durée choisie par l’enfant est reprise', () => {
    const workspace = new Blockly.Workspace();
    chain(workspace, 'go2_move_forward');
    find(workspace, 'go2_move_forward').setFieldValue('5', 'DURATION');
    expect(first(workspace)).toEqual({
      kind: 'move',
      direction: 'forward',
      seconds: 5,
      line: expect.any(Number),
    });
  });

  it.each([
    ['go2_turn_left', 'left'],
    ['go2_turn_right', 'right'],
  ])('%s devient une rotation %s', (type, direction) => {
    const workspace = new Blockly.Workspace();
    chain(workspace, type);
    expect(first(workspace)).toMatchObject({ kind: 'turn', direction });
  });

  it('l’angle choisi est repris', () => {
    const workspace = new Blockly.Workspace();
    chain(workspace, 'go2_turn_left');
    find(workspace, 'go2_turn_left').setFieldValue('180', 'ANGLE');
    expect(first(workspace)).toMatchObject({ kind: 'turn', degrees: 180 });
  });

  it('« Arrêter le robot » devient une instruction dédiée', () => {
    const workspace = new Blockly.Workspace();
    chain(workspace, 'go2_stop_move');
    expect(first(workspace)).toMatchObject({ kind: 'stop_move' });
  });

  it('aucune consigne de vitesse n’est produite', () => {
    // La vitesse est une décision du service : si elle sortait d'ici, un
    // enfant pourrait la porter au-delà de la limite de sécurité.
    const workspace = new Blockly.Workspace();
    chain(workspace, 'go2_move_forward');
    expect(JSON.stringify(first(workspace))).not.toMatch(/speed|vitesse/);
  });
});

describe('actions', () => {
  it.each([
    ['go2_stand_up', 'stand'],
    ['go2_sit_down', 'sit'],
    ['go2_balance', 'balance'],
  ])('%s devient la posture %s', (type, posture) => {
    const workspace = new Blockly.Workspace();
    chain(workspace, type);
    expect(first(workspace)).toMatchObject({ kind: 'posture', posture });
  });
});

describe('contrôle', () => {
  it('« Attendre » reprend le choix', () => {
    const workspace = new Blockly.Workspace();
    chain(workspace, 'go2_wait');
    find(workspace, 'go2_wait').setFieldValue('3', 'SECONDS');
    expect(first(workspace)).toMatchObject({ kind: 'wait', seconds: 3 });
  });

  it('« Répéter » garde son corps', () => {
    const workspace = new Blockly.Workspace();
    const loop = workspace.newBlock('go2_repeat');
    loop.setFieldValue('5', 'COUNT');
    loop.getInput('DO')!.connection!.connect(
      workspace.newBlock('go2_move_forward').previousConnection!,
    );
    attach(workspace, loop);

    const statement = first(workspace);
    expect(statement.kind).toBe('repeat');
    if (statement.kind !== 'repeat') throw new Error('attendu : repeat');
    expect(statement.times).toBe(5);
    expect(statement.body).toHaveLength(1);
  });

  it('« Si … sinon » garde ses deux branches', () => {
    const workspace = new Blockly.Workspace();
    const branch = workspace.newBlock('go2_if_else');
    branch
      .getInput('DO')!
      .connection!.connect(workspace.newBlock('go2_stand_up').previousConnection!);
    branch
      .getInput('ELSE')!
      .connection!.connect(workspace.newBlock('go2_sit_down').previousConnection!);
    attach(workspace, branch);

    const statement = first(workspace);
    expect(statement.kind).toBe('if');
    if (statement.kind !== 'if') throw new Error('attendu : if');
    expect(statement.then.map((s) => s.kind)).toEqual(['posture']);
    expect(statement.otherwise?.map((s) => s.kind)).toEqual(['posture']);
  });

  it('la condition choisie est transmise telle quelle', () => {
    // Le compilateur ne peut PAS dire si la batterie est faible : il
    // transmet, le service tranchera avec la valeur réellement lue.
    for (const condition of ['posture_stand', 'battery_low']) {
      const workspace = new Blockly.Workspace();
      const branch = workspace.newBlock('go2_if');
      branch.setFieldValue(condition, 'CONDITION');
      attach(workspace, branch);
      expect(first(workspace)).toMatchObject({ kind: 'if', condition });
    }
  });

  it('« Arrêter le programme » devient une instruction dédiée', () => {
    const workspace = new Blockly.Workspace();
    chain(workspace, 'go2_wait', 'go2_stop_program');
    expect(compileWorkspace(workspace).program.statements.map((s) => s.kind)).toEqual([
      'wait',
      'stop_program',
    ]);
  });
});

describe('menus : une valeur forgée n’atteint jamais le robot', () => {
  /**
   * Deux barrières successives, toutes deux vérifiées ici.
   *
   * 1. Blockly refuse lui-même une valeur absente du menu et conserve la
   *    précédente : c'est la barrière la plus proche de l'écran.
   * 2. Le compilateur revérifie la valeur : barrière indépendante, utile si
   *    quelqu'un contourne Blockly en appelant directement l'API HTTP.
   *
   * L'important n'est pas *laquelle* arrête la valeur, mais qu'aucune ne
   * passe.
   */

  /**
   * Simule un client qui contourne Blockly et envoie directement la valeur.
   *
   * `FieldDropdown` refuse par lui-même une valeur absente du menu, mais ce
   * n'est pas une garantie de sécurité : il suffit d'appeler l'API HTTP, ou
   * de modifier un état en mémoire, pour la présenter au compilateur. On
   * remplace donc la lecture du champ.
   */
  function forge(workspace: Blockly.Workspace, type: string, field: string, value: string) {
    const block = find(workspace, type);
    (block as unknown as { getFieldValue: (n: string) => unknown }).getFieldValue = (
      name: string,
    ) => (name === field ? value : undefined);
  }

  it('la durée forgée ne devient pas une consigne', () => {
    const workspace = new Blockly.Workspace();
    chain(workspace, 'go2_move_forward');
    forge(workspace, 'go2_move_forward', 'DURATION', '10000');

    const result = compileWorkspace(workspace);
    expect(result.issues.length).toBeGreaterThan(0);
    expect(result.program.statements[0]).toMatchObject({ seconds: 2 });
  });

  it('l’angle forgé ne devient pas une consigne', () => {
    const workspace = new Blockly.Workspace();
    chain(workspace, 'go2_turn_left');
    forge(workspace, 'go2_turn_left', 'ANGLE', '100000');

    const result = compileWorkspace(workspace);
    expect(result.issues.length).toBeGreaterThan(0);
    expect(result.program.statements[0]).toMatchObject({ degrees: 90 });
  });

  it('un nombre de répétitions forgé ne devient pas une boucle', () => {
    const workspace = new Blockly.Workspace();
    const loop = workspace.newBlock('go2_repeat');
    attach(workspace, loop);
    forge(workspace, 'go2_repeat', 'COUNT', '9999');

    const result = compileWorkspace(workspace);
    expect(result.issues.length).toBeGreaterThan(0);
    expect(result.program.statements[0]).toMatchObject({ times: 3 });
  });

  it('une condition non proposée n’est jamais transmise', () => {
    // « obstacle_detected » n'existe pas : le service le refuserait de son
    // côté, mais il ne doit même pas sortir du frontend.
    const workspace = new Blockly.Workspace();
    const branch = workspace.newBlock('go2_if');
    attach(workspace, branch);
    forge(workspace, 'go2_if', 'CONDITION', 'obstacle_detected');

    const result = compileWorkspace(workspace);
    expect(result.issues.length).toBeGreaterThan(0);
    expect(result.program.statements[0]).toMatchObject({ condition: 'posture_stand' });
  });

  it('le menu de Blockly refuse déjà une valeur absente des choix', () => {
    // Première barrière, au plus près de l'écran : le menu lui-même.
    const workspace = new Blockly.Workspace();
    const menu = new Blockly.FieldDropdown([['1 seconde', '1'], ['2 secondes', '2']]);
    menu.setValue('2');
    menu.setValue('0.25');
    expect(menu.getValue()).toBe('2');
  });

  it('un fichier de mission bricolé ne fait pas passer une durée interdite', () => {
    // Chemin d'attaque réel : un fichier XML modifié à la main.
    const workspace = new Blockly.Workspace();
    Blockly.Xml.domToWorkspace(
      Blockly.utils.xml.textToDom(
        [
          '<xml xmlns="https://developers.google.com/blockly/xml">',
          '  <block type="go2_start"><next>',
          '    <block type="go2_move_forward">',
          '      <field name="DURATION">0.25</field>',
          '    </block>',
          '  </next></block>',
          '</xml>',
        ].join('\n'),
      ),
      workspace,
    );

    const result = compileWorkspace(workspace);
    // Blockly a conservé la valeur proposée par défaut, donc rien d'impossible
    // n'atteint le programme.
    expect(result.program.statements[0]).toMatchObject({ seconds: 2 });
  });
});

describe('robustesse', () => {
  it('signale un programme sans bloc de départ', () => {
    const workspace = new Blockly.Workspace();
    workspace.newBlock('go2_wait');
    const result = compileWorkspace(workspace);
    expect(result.hasStart).toBe(false);
    expect(result.program.statements).toEqual([]);
    expect(result.issues.length).toBeGreaterThan(0);
  });

  it('signale un bloc seul, non accroché', () => {
    const workspace = new Blockly.Workspace();
    chain(workspace, 'go2_wait');
    workspace.newBlock('go2_stand_up');
    expect(compileWorkspace(workspace).issues.some((i) => i.message.includes('seul'))).toBe(
      true,
    );
  });

  it('ne boucle pas sur un cycle', () => {
    const workspace = new Blockly.Workspace();
    chain(workspace, 'go2_wait');
    const wait = find(workspace, 'go2_wait');
    wait.nextConnection!.connect(wait.previousConnection!);
    expect(() => compileWorkspace(workspace)).not.toThrow();
  });

  it('signale un bloc inconnu au lieu de l’ignorer', () => {
    Blockly.Blocks['go2_fantome'] = {
      init(this: Blockly.Block) {
        this.setPreviousStatement(true);
        this.setNextStatement(true);
        this.appendDummyInput().appendField('Bloc inexistant');
      },
    };
    try {
      const workspace = new Blockly.Workspace();
      chain(workspace, 'go2_fantome');
      const result = compileWorkspace(workspace);
      expect(result.issues.some((i) => i.message.includes('n’est pas reconnu'))).toBe(true);
      expect(result.program.statements).toHaveLength(0);
    } finally {
      delete Blockly.Blocks['go2_fantome'];
    }
  });
});

describe('affichage des étapes', () => {
  it('développe les répétitions pour lister les étapes', () => {
    const workspace = new Blockly.Workspace();
    const loop = workspace.newBlock('go2_repeat');
    loop.setFieldValue('5', 'COUNT');
    loop
      .getInput('DO')!
      .connection!.connect(workspace.newBlock('go2_wait').previousConnection!);
    attach(workspace, loop);

    const { program } = compileWorkspace(workspace);
    // Le programme TRANSPORTÉ reste structuré…
    expect(program.statements).toHaveLength(1);
    expect(program.statements[0]!.kind).toBe('repeat');
    // …tandis que la liste des étapes en montre cinq.
    expect(flattenForDisplay(program.statements)).toHaveLength(5);
    expect(countSteps(program.statements)).toBe(5);
  });

  it('une condition compte pour une seule étape', () => {
    // On ne peut pas savoir quelle branche sera prise : annoncer les deux
    // ferait voir à l'enfant des mouvements qui n'auront pas lieu.
    const workspace = new Blockly.Workspace();
    const branch = workspace.newBlock('go2_if_else');
    branch
      .getInput('DO')!
      .connection!.connect(workspace.newBlock('go2_wait').previousConnection!);
    branch
      .getInput('ELSE')!
      .connection!.connect(workspace.newBlock('go2_stand_up').previousConnection!);
    attach(workspace, branch);

    expect(flattenForDisplay(compileWorkspace(workspace).program.statements)).toHaveLength(1);
  });
});