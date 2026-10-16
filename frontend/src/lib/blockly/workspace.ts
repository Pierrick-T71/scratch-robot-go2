/**
 * Initialisation de l'editeur Blockly : locale francaise + palette.
 *
 * L'import de `blockly/blocks` charge les blocs standards Blockly (utilises
 * ici pour l'echelle et les valeurs numeriques). Les blocs GO2 sont declares
 * a part dans `blocks.ts`.
 */
import * as Blockly from 'blockly/core';
import * as Fr from 'blockly/msg/fr';
import 'blockly/blocks';

import {
  CATEGORIES,
  BLOCK_DEFINITIONS,
  registerGo2Blocks,
  FIELD_BOUNDS,
} from './blocks';

export { Blockly, FIELD_BOUNDS };

let localeApplied = false;

/**
 * Applique la locale francaise. A appeler avant `Blockly.inject`.
 *
 * `blockly/msg/fr` (module ESM) reexporte les cles de message une a une
 * (`export const { LOGIC_HUE, ... } = fr`) : le namespace EST l'objet de
 * messages. En revanche le fichier `.d.ts` publie un `default` qui ne
 * correspond pas a cette forme runtime, d'ou le cast ci-dessous. Ce n'est
 * qu'un contournement de typage, aucun `default` n'est lu a l'execution.
 */
export function applyFrenchLocale(): void {
  if (localeApplied) return;
  Blockly.setLocale(Fr as unknown as Record<string, string>);
  localeApplied = true;
}

/**
 * Definition JSON de la palette, telle que attendue par `options.toolbox`.
 * Le type officiel `ToolboxDefinition` n'est pas reexporte par `blockly/core`,
 * on declare donc la forme locale utile a l'application.
 */
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

/**
 * Palette de blocs, en francais.
 *
 * En Blockly 13, `options.toolbox` attend une definition JSON, pas une
 * instance de `Toolbox` (qui se construit toute seule a l'injection).
 * Le libelle de categorie est le nom de la categorie : comportement natif,
 * aucun callback supplementaire.
 */
export function buildToolbox(): ToolboxDefinitionJson {
  return {
    kind: 'categoryToolbox',
    contents: CATEGORIES.map((category) => ({
      kind: 'category',
      name: category.label,
      colour: category.colour,
      contents: BLOCK_DEFINITIONS.filter((d) => d.category === category.name).map((d) => ({
        kind: 'block',
        type: d.type,
      })),
    })),
  };
}

/** Options d'injection Blockly pour GO2 Scratch. */
export function buildInjectOptions(): Blockly.BlocklyOptions {
  registerGo2Blocks();
  return {
    // La forme JSON est structurellement compatible avec `ToolboxDefinition`.
    toolbox: buildToolbox(),
    trashcan: true,
    sounds: false,
    grid: { spacing: 24, length: 3, colour: '#E2E8F0', snap: true },
    zoom: { controls: true, wheel: true, startScale: 0.9, minScale: 0.4, maxScale: 1.6 },
    move: { scrollbars: true, drag: true, wheel: true },
    renderer: 'geras',
  };
}

/**
 * Programme de depart propose a l'ouverture : uniquement le bloc de depart,
 * pour que l'enfant ajoute lui-meme ses blocs.
 */
export function defaultProgramXml(): string {
  return [
    '<xml xmlns="https://developers.google.com/blockly/xml">',
    '  <block type="go2_start" x="40" y="40"></block>',
    '</xml>',
  ].join('\n');
}