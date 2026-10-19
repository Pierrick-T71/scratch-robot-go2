/**
 * Locale française de Blockly.
 *
 * Isolé dans son propre module pour éviter une dépendance circulaire :
 * `blocks.ts` a besoin de la locale (voir `registerGo2Blocks`) et
 * `workspace.ts` en a besoin aussi, alors aucun des deux ne peut importer
 * l'autre.
 *
 * ## Pourquoi c'est obligatoire, et pas cosmétique
 *
 * `FieldVariable` construit son menu déroulant en lisant un message
 * localisé puis en appelant `.replace()` dessus. Sans locale appliquée, ce
 * message vaut `undefined` et la création du bloc **lève une exception**.
 * Conséquence observée : tous les blocs de variables et de messages
 * s'affichaient muets et n'enregistraient aucun champ.
 *
 * `registerGo2Blocks()` appelle donc `applyFrenchLocale()` lui-même, pour
 * qu'aucun appelant ne puisse l'oublier.
 */
import * as Blockly from 'blockly/core';
import * as Fr from 'blockly/msg/fr';

let applied = false;

/**
 * Applique la locale française. Idempotent.
 *
 * `blockly/msg/fr` réexporte les clés de message une à une
 * (`export const { LOGIC_HUE, … } = fr`) : le namespace EST l'objet de
 * messages. Le fichier `.d.ts` publie en revanche un `default` qui ne
 * correspond pas à cette forme d'exécution ; d'où le cast, qui ne porte que
 * sur le typage.
 */
export function applyFrenchLocale(): void {
  if (applied) return;
  Blockly.setLocale(Fr as unknown as Record<string, string>);
  applied = true;
}

/** `true` si la locale a déjà été appliquée. Réservé aux tests. */
export function isFrenchLocaleApplied(): boolean {
  return applied;
}