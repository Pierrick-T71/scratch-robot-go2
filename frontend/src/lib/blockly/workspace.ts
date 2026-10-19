/**
 * Palette de blocs et options d'injection.
 *
 * En Blockly 13, `options.toolbox` attend une définition JSON ; le libellé de
 * catégorie est le nom de la catégorie. Aucune clé `shadow`, aucun bloc
 * variable : la palette ne contient que ce qui est proposé aux enfants.
 */
import * as Blockly from 'blockly/core';
import 'blockly/blocks';

import { BLOCK_DEFINITIONS, CATEGORIES, CATEGORY_COLOURS, registerGo2Blocks } from './blocks';
import { applyFrenchLocale } from './locale';

export { Blockly, CATEGORIES, BLOCK_DEFINITIONS, registerGo2Blocks, applyFrenchLocale };
export { CATEGORY_COLOURS } from './blocks';

/** Catégories de la palette, telles que Blockly les attend. */
export interface ToolboxCategory {
  kind: 'category';
  name: string;
  colour: string;
  contents: Array<{ kind: 'block'; type: string }>;
}

export interface ToolboxDefinitionJson {
  kind: 'categoryToolbox';
  contents: ToolboxCategory[];
}

/** Palette de blocs, en français. */
export function buildToolbox(): ToolboxDefinitionJson {
  return {
    kind: 'categoryToolbox',
    contents: CATEGORIES.map((category) => ({
      kind: 'category',
      name: category.label,
      colour: CATEGORY_COLOURS[category.name],
      contents: BLOCK_DEFINITIONS.filter((d) => d.category === category.name).map((d) => ({
        kind: 'block',
        type: d.type,
      })),
    })),
  };
}

/**
 * Options d'injection Blockly pour GO2 Scratch.
 *
 * `zoom` et la grille restent activés : un enfant doit pouvoir voir un bloc
 * entier sans zoomer à la molette.
 */
export function buildInjectOptions(): Blockly.BlocklyOptions {
  registerGo2Blocks();
  return {
    toolbox: buildToolbox(),
    trashcan: true,
    sounds: false,
    grid: { spacing: 26, length: 3, colour: '#E2E8F0', snap: true },
    zoom: { controls: true, wheel: true, startScale: 0.9, minScale: 0.5, maxScale: 1.6 },
    move: { scrollbars: true, drag: true, wheel: true },
    renderer: 'geras',
  };
}

/**
 * Programme de départ proposé à l'ouverture.
 *
 * On part d'un exemple court et comprehensible plutôt que d'un bloc nu :
 * l'enfant voit tout de suite à quoi ressemble un programme.
 */
export function defaultProgramXml(): string {
  return [
    '<xml xmlns="https://developers.google.com/blockly/xml">',
    '  <block type="go2_start" x="40" y="40">',
    '    <next>',
    '      <block type="go2_move_forward">',
    '        <field name="DURATION">2</field>',
    '        <next>',
    '          <block type="go2_turn_left">',
    '            <field name="ANGLE">90</field>',
    '          </block>',
    '        </next>',
    '      </block>',
    '    </next>',
    '  </block>',
    '</xml>',
  ].join('\n');
}