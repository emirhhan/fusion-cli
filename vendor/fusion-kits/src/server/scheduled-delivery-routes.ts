import { Hono } from 'hono';
import type { Store } from './store.js';
import type { Platform } from './platform.js';
import { deliverySchema, deliverSchedule } from './scheduled-delivery.js';
export function scheduledDeliveryRoutes(
  store: Store,
  platform?: Pick<Platform, 'workspace' | 'fusion'>,
): Hono {
  const app = new Hono();
  app.post('/scheduled-deliveries', async (c) => {
    const body: unknown = await c.req.json().catch(() => null);
    const parsed = deliverySchema.safeParse(body);
    if (!parsed.success)
      return c.json({ error: 'Teslim girdileri geçersiz.' }, 400);
    if (!platform)
      return c.json({ error: 'Fusion çalışma alanı bağlı değil.' }, 409);
    try {
      return c.json(
        deliverSchedule(
          store,
          platform.workspace,
          platform.fusion,
          parsed.data,
        ),
      );
    } catch (error) {
      return c.json(
        { error: error instanceof Error ? error.message : 'Teslim başarısız.' },
        409,
      );
    }
  });
  return app;
}
