import {
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  useSyncExternalStore,
} from 'react';
import type { Page } from '../../server/pages';
import { api } from '../api';
import { PageAutosave } from './autosave';
import { PageDraftStore } from './page-draft-store';
import { bindPageDraft } from './page-draft-session';
export function usePageAutosave(
  page: Page,
  onSaved: (page: Page) => void,
  ownerId?: string,
) {
  const savedCallback = useRef(onSaved);
  const [controller] = useState(() => {
    const instance = new PageAutosave(
      async (id, patch, signal, scope) => {
        return api<Page>(
          `/spaces/${scope.spaceId}/pages/${id}`,
          'PATCH',
          patch,
          signal,
        );
      },
      (saved) => savedCallback.current(saved),
    );
    instance.receive(page);
    return instance;
  });
  const state = useSyncExternalStore(
    controller.subscribe,
    controller.getSnapshot,
    controller.getSnapshot,
  );
  useLayoutEffect(() => {
    savedCallback.current = onSaved;
    controller.receive(page);
  }, [controller, page, onSaved]);
  useEffect(() => () => controller.dispose(), [controller]);
  useLayoutEffect(() => {
    if (!ownerId) {
      controller.storageWarning(
        'Yerel taslak hesabı doğrulanamadı. Kapatmadan önce kaydet veya taslağını indir.',
      );
      return;
    }
    try {
      const store = new PageDraftStore(window.localStorage, navigator.locks);
      const session = bindPageDraft(controller, store, {
        ownerId,
        spaceId: page.spaceId,
        pageId: page.id,
      });
      return () => session.dispose();
    } catch {
      controller.storageWarning(
        'Yerel taslak saklama kullanılamıyor. Kapatmadan önce kaydet veya taslağını indir.',
      );
    }
  }, [controller, ownerId, page.spaceId, page.id]);
  return { controller, state };
}
