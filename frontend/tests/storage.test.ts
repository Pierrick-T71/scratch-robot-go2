/**
 * Sauvegarde et rechargement d'un programme.
 *
 * Un enfant retrouve sa mission demain. Si les choix faits (durée, angle,
 * condition) disparaissent au rechargement, il perd son travail sans qu'on
 * lui dise pourquoi — c'est le défaut le plus irritant de ce type
 * d'application.
 */
import { describe, it, expect, beforeAll } from 'vitest';
import * as Blockly from 'blockly/core';
import 'blockly/blocks';
import { registerGo2Blocks } from '../src/lib/blockly/blocks';
import { compileWorkspace } from '../src/lib/blockly/compiler';
import { defaultProgramXml } from '../src/lib/blockly/workspace';

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

/** Sérialise puis recharge, comme le fait l'application. */
function roundTrip(workspace: Blockly.Workspace): Blockly.Workspace {
  const xml = Blockly.Xml.domToText(Blockly.Xml.workspaceToDom(workspace, false));
  const reloaded = new Blockly.Workspace();
  Blockly.Xml.domToWorkspace(Blockly.utils.xml.textToDom(xml), reloaded);
  return reloaded;
}

/** Programme sans le numéro de ligne, qui change à chaque identifiant. */
function shape(workspace: Blockly.Workspace): unknown[] {
  return JSON.parse(
    JSON.stringify(compileWorkspace(workspace).program.statements, (_key, value) =>
      _key === 'line' ? undefined : value,
    ),
  );
}

describe('programme de référence', () => {
  it('survit à un enregistrement puis rechargement', () => {
    const original = new Blockly.Workspace();
    chain(original, 'go2_move_forward', 'go2_turn_left', 'go2_move_forward', 'go2_stop_move');

    const reloaded = roundTrip(original);
    expect(shape(reloaded)).toEqual(shape(original));
  });

  it('conserve les choix faits par l’enfant', () => {
    const original = new Blockly.Workspace();
    chain(original, 'go2_move_forward', 'go2_turn_left', 'go2_wait');
    const move = original.getAllBlocks(false).find((b) => b.type === 'go2_move_forward')!;
    const turn = original.getAllBlocks(false).find((b) => b.type === 'go2_turn_left')!;
    const attente = original.getAllBlocks(false).find((b) => b.type === 'go2_wait')!;
    move.setFieldValue('5', 'DURATION');
    turn.setFieldValue('180', 'ANGLE');
    attente.setFieldValue('3', 'SECONDS');

    const reloaded = roundTrip(original);
    const statements = compileWorkspace(reloaded).program.statements;
    expect(statements[0]).toMatchObject({ kind: 'move', seconds: 5 });
    expect(statements[1]).toMatchObject({ kind: 'turn', degrees: 180 });
    expect(statements[2]).toMatchObject({ kind: 'wait', seconds: 3 });
  });
});

describe('structures', () => {
  it('conserve une boucle et son corps', () => {
    const original = new Blockly.Workspace();
    const loop = original.newBlock('go2_repeat');
    loop.setFieldValue('10', 'COUNT');
    loop
      .getInput('DO')!
      .connection!.connect(original.newBlock('go2_wait').previousConnection!);
    const start = original.newBlock('go2_start');
    start.nextConnection!.connect(loop.previousConnection!);

    const statements = compileWorkspace(roundTrip(original)).program.statements;
    expect(statements[0]).toMatchObject({ kind: 'repeat', times: 10 });
    if (statements[0]!.kind !== 'repeat') throw new Error('attendu : repeat');
    expect(statements[0]!.body).toHaveLength(1);
  });

  it('conserve les deux branches d’un « Si … sinon »', () => {
    const original = new Blockly.Workspace();
    const branch = original.newBlock('go2_if_else');
    branch.setFieldValue('battery_low', 'CONDITION');
    branch
      .getInput('DO')!
      .connection!.connect(original.newBlock('go2_stop_move').previousConnection!);
    branch
      .getInput('ELSE')!
      .connection!.connect(original.newBlock('go2_stand_up').previousConnection!);
    const start = original.newBlock('go2_start');
    start.nextConnection!.connect(branch.previousConnection!);

    const statements = compileWorkspace(roundTrip(original)).program.statements;
    expect(statements[0]).toMatchObject({ kind: 'if', condition: 'battery_low' });
    if (statements[0]!.kind !== 'if') throw new Error('attendu : if');
    expect(statements[0]!.then).toHaveLength(1);
    expect(statements[0]!.otherwise).toHaveLength(1);
  });

  it('imbrique plusieurs boucles', () => {
    const original = new Blockly.Workspace();
    const outer = original.newBlock('go2_repeat');
    const inner = original.newBlock('go2_repeat');
    outer.getInput('DO')!.connection!.connect(inner.previousConnection!);
    inner
      .getInput('DO')!
      .connection!.connect(original.newBlock('go2_wait').previousConnection!);
    const start = original.newBlock('go2_start');
    start.nextConnection!.connect(outer.previousConnection!);

    const statements = compileWorkspace(roundTrip(original)).program.statements;
    expect(statements[0]!.kind).toBe('repeat');
    if (statements[0]!.kind !== 'repeat') throw new Error('attendu : repeat');
    expect(statements[0]!.body[0]!.kind).toBe('repeat');
  });
});

describe('programme de départ', () => {
  it('est complet et se compile sans erreur', () => {
    const workspace = new Blockly.Workspace();
    Blockly.Xml.domToWorkspace(
      Blockly.utils.xml.textToDom(defaultProgramXml()),
      workspace,
    );

    const result = compileWorkspace(workspace);
    expect(result.hasStart).toBe(true);
    expect(result.issues).toEqual([]);
    expect(result.program.statements.map((s) => s.kind)).toEqual(['move', 'turn']);
  });

  it('montre à l’enfant un exemple, pas une page blanche', () => {
    // Un enfant doit voir tout de suite à quoi ressemble un programme.
    expect(defaultProgramXml()).toContain('go2_start');
    expect(defaultProgramXml()).toContain('go2_move_forward');
  });

  it('survit lui aussi à un aller-retour', () => {
    const workspace = new Blockly.Workspace();
    Blockly.Xml.domToWorkspace(
      Blockly.utils.xml.textToDom(defaultProgramXml()),
      workspace,
    );
    expect(shape(roundTrip(workspace))).toEqual(shape(workspace));
  });
});

describe('robustesse du rechargement', () => {
  it('un fichier illisible ne casse pas l’éditeur', () => {
    const workspace = new Blockly.Workspace();
    // L'application retombe sur le programme de départ plutôt que de laisser
    // un état partiel.
    expect(() => Blockly.Xml.domToWorkspace(
      Blockly.utils.xml.textToDom('<xml><pas-un-bloc/></xml>'),
      workspace,
    )).not.toThrow();
  });

  it('un fichier sans bloc de départ est signalé, pas silencieusement exécuté', () => {
    const workspace = new Blockly.Workspace();
    chain(workspace, 'go2_move_forward');
    const xml = Blockly.Xml.domToText(Blockly.Xml.workspaceToDom(workspace, false));

    const reloaded = new Blockly.Workspace();
    // On retire le bloc de départ du XML chargé.
    Blockly.Xml.domToWorkspace(Blockly.utils.xml.textToDom(xml), reloaded);
    for (const block of [...reloaded.getAllBlocks(false)]) {
      if (block.type === 'go2_start') block.dispose();
    }

    const result = compileWorkspace(reloaded);
    expect(result.hasStart).toBe(false);
    expect(result.issues.length).toBeGreaterThan(0);
  });
});