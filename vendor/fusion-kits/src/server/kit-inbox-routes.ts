import { Hono } from 'hono';
import type { Store } from './store.js';
import type { WorkspaceStore } from './workspace.js';
import {
  deliverToKit,
  inboxDetail,
  inboxItems,
  inboxSchema,
  kitSummaries,
  KitInboxError,
  resolveKit,
  type CreateConversation,
} from './kit-inbox.js';

export interface KitInboxPlatform {
  readonly workspace: WorkspaceStore;
  createConversation: CreateConversation;
}

/**
 * Fusion'ın Kits'e konuştuğu yerel uçlar (`/api` altına bağlanır; aynı sahip/origin
 * ara katmanından geçer). Kit `:ref` kimlik ya da ad olabilir.
 */
export function kitInboxRoutes(store: Store, platform: KitInboxPlatform): Hono {
  const app = new Hono();
  const fail = (error: unknown) => {
    if (error instanceof KitInboxError)
      return { body: { error: error.message }, status: error.status };
    return {
      body: {
        error:
          error instanceof Error && /[çğıöşüÇĞİÖŞÜ]/.test(error.message)
            ? error.message
            : 'Gelen kutusu isteği tamamlanamadı.',
      },
      status: 503 as const,
    };
  };
  app.get('/kits', (c) => c.json({ kits: kitSummaries(platform.workspace) }));
  app.get('/kits/:ref/inbox', (c) => {
    try {
      const dot = resolveKit(platform.workspace, c.req.param('ref'));
      return c.json({
        kitId: dot.id,
        items: inboxItems(store, platform.workspace, dot),
      });
    } catch (error) {
      const { body, status } = fail(error);
      return c.json(body, status);
    }
  });
  app.post('/kits/:ref/inbox', async (c) => {
    const parsed = inboxSchema.safeParse(await c.req.json().catch(() => null));
    if (!parsed.success)
      return c.json(
        { error: '3 ile 4.000 karakter arasında bir metin gir.' },
        400,
      );
    try {
      const dot = resolveKit(platform.workspace, c.req.param('ref'));
      return c.json(
        await deliverToKit(
          store,
          platform.workspace,
          (dotId, title) => platform.createConversation(dotId, title),
          dot,
          parsed.data,
        ),
        201,
      );
    } catch (error) {
      const { body, status } = fail(error);
      return c.json(body, status);
    }
  });
  app.get('/kits/:ref/inbox/:taskId', (c) => {
    try {
      const dot = resolveKit(platform.workspace, c.req.param('ref'));
      const detail = inboxDetail(
        store,
        platform.workspace,
        dot,
        c.req.param('taskId'),
      );
      return detail
        ? c.json(detail)
        : c.json({ error: 'Gelen kutusu görevi bulunamadı.' }, 404);
    } catch (error) {
      const { body, status } = fail(error);
      return c.json(body, status);
    }
  });
  return app;
}
