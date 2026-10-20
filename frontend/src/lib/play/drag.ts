/**
 * Glisser-déposer entre la bibliothèque et la timeline.
 *
 * Le type MIME est propre à l'application : un fichier venu d'ailleurs ne
 * doit pas être accepté comme un bloc. `text/plain` est renseigné en plus,
 * car certains navigateurs refusent un dépôt sans type standard.
 */
import type { PlayBlockKind } from './blocks';

export const DRAG_MIME = 'application/x-go2-block';

export type DragPayload =
  | { source: 'library'; kind: PlayBlockKind }
  | { source: 'timeline'; id: string };

export function setDragPayload(event: DragEvent, payload: DragPayload): void {
  const transfer = event.dataTransfer;
  if (!transfer) return;
  const text = JSON.stringify(payload);
  transfer.setData(DRAG_MIME, text);
  transfer.setData('text/plain', text);
  transfer.effectAllowed = payload.source === 'library' ? 'copy' : 'move';
}

export function readDragPayload(event: DragEvent): DragPayload | null {
  const transfer = event.dataTransfer;
  if (!transfer) return null;
  const text = transfer.getData(DRAG_MIME) || transfer.getData('text/plain');
  if (!text) return null;
  try {
    const parsed: unknown = JSON.parse(text);
    if (typeof parsed !== 'object' || parsed === null) return null;
    const raw = parsed as Record<string, unknown>;
    if (raw['source'] === 'library' && typeof raw['kind'] === 'string') {
      return { source: 'library', kind: raw['kind'] as PlayBlockKind };
    }
    if (raw['source'] === 'timeline' && typeof raw['id'] === 'string') {
      return { source: 'timeline', id: raw['id'] };
    }
    return null;
  } catch {
    return null;
  }
}
