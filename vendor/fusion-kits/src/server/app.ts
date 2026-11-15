import { scheduledDeliveryRoutes } from './scheduled-delivery-routes.js';
import { fusionRoutes } from './fusion/routes.js';
import { computerRoutes } from './computer-routes.js';
import { kitInboxRoutes } from './kit-inbox-routes.js';
import { Hono } from 'hono';
import { bodyLimit } from 'hono/body-limit';
import { timingSafeEqual } from 'node:crypto';
import { z } from 'zod';
import { Store } from './store.js';
import { Runner } from './runner.js';
import { configured, type Config } from './research.js';
import type { Platform } from './platform.js';
import { VoiceService } from './voice.js';
import { workspaceRoutes } from './workspace-routes.js';
const interval = z.number().int().min(60).max(31_536_000).nullable();
export interface AppOptions {
  store: Store;
  runner: Runner;
  config: Config;
  ownerToken?: string;
  origin?: string;
  platform?: Platform;
}
export function createApp({
  store,
  runner,
  config,
  ownerToken,
  origin,
  platform,
}: AppOptions) {
  const app = new Hono();
  app.use(
    '/api/*',
    bodyLimit({
      maxSize: 1_000_000,
      onError: (c) => c.json({ error: 'İstek çok büyük.' }, 413),
    }),
  );
  app.use('/api/*', async (c, next) => {
    c.header('Cache-Control', 'no-store');
    c.header('X-Content-Type-Options', 'nosniff');
    const requestUrl = new URL(c.req.url);
    const allowedHosts = new Set([
      'localhost',
      '127.0.0.1',
      '[::1]',
      ...(origin ? [new URL(origin).hostname] : []),
    ]);
    if (!ownerToken && !allowedHosts.has(requestUrl.hostname))
      return c.json({ error: 'Tanınmayan ana makine.' }, 403);
    const requestOrigin = c.req.header('origin');
    const expectedOrigin = origin ?? new URL(c.req.url).origin;
    if (requestOrigin && requestOrigin !== expectedOrigin)
      return c.json({ error: 'Çapraz kaynaklı isteklere izin verilmez.' }, 403);
    if (c.req.header('sec-fetch-site') === 'cross-site')
      return c.json({ error: 'Siteler arası isteklere izin verilmez.' }, 403);
    if (ownerToken) {
      const expected = Buffer.from(ownerToken);
      const supplied = Buffer.from(
        c.req.header('authorization')?.replace(/^Bearer /, '') ?? '',
      );
      if (
        expected.length !== supplied.length ||
        !timingSafeEqual(expected, supplied)
      )
        return c.json(
          { error: 'Kits kilidini açmak için sahip erişim anahtarını gir.' },
          401,
        );
    }
    if (
      !['GET', 'HEAD'].includes(c.req.method) &&
      !c.req.header('content-type')?.includes('application/json')
    )
      return c.json({ error: 'application/json kullan.' }, 415);
    await next();
  });
  app.route('/api', scheduledDeliveryRoutes(store, platform));
  if (platform) {
    app.route('/api', fusionRoutes(platform.fusion));
    app.route('/api', computerRoutes(platform.computers));
    // Fusion → Kit gelen kutusu (P-063): aynı sahip/origin ara katmanından geçer.
    app.route('/api', kitInboxRoutes(store, platform));
  }
  const voice = platform ? new VoiceService(platform) : undefined;
  if (platform && voice) app.route('/api', workspaceRoutes(platform, voice));
  app.get('/api/state', (c) =>
    c.json({
      settings: store.settings(),
      tasks: store.tasks(),
      memories: store.memories(),
      mode: config.mode,
      configured: configured(config),
    }),
  );
  app.post('/api/tasks', async (c) => {
    const parsed = z
      .object({
        prompt: z.string().trim().min(3).max(4000),
        intervalSeconds: interval.optional(),
        threadId: z.string().optional(),
      })
      .strict()
      .safeParse(await c.req.json().catch(() => null));
    if (!parsed.success)
      return c.json(
        {
          error:
            '3 ile 4.000 karakter arasında bir istek gir; tekrar aralığı en az 60 saniye olmalı.',
        },
        400,
      );
    if (!store.settings().researchAllowed)
      return c.json({ error: 'Araştırma Ayarlar’da kapalı.' }, 403);
    if (platform) {
      if (platform.setup().missing.length)
        return c.json(
          { error: `Kurulum gerekli: ${platform.setup().missing.join(', ')}.` },
          503,
        );
      if (!parsed.data.threadId)
        return c.json(
          { error: 'Bu zamanlanmış görev için bir sohbet seç.' },
          400,
        );
      try {
        platform.workspace.requireThread(parsed.data.threadId);
      } catch {
        return c.json({ error: 'Sohbet bu çalışma alanına ait değil.' }, 403);
      }
    }
    const task = store.createTask(
      parsed.data.prompt,
      parsed.data.intervalSeconds,
    );
    if (platform && parsed.data.threadId)
      platform.workspace.bindTask(task.id, parsed.data.threadId);
    return c.json(task, 201);
  });
  app.get('/api/tasks/:id', (c) => {
    const detail = store.detail(c.req.param('id'));
    return detail
      ? c.json(detail)
      : c.json({ error: 'Görev bulunamadı.' }, 404);
  });
  app.post('/api/tasks/:id/actions', async (c) => {
    const parsed = z
      .object({ action: z.enum(['run', 'pause', 'cancel']) })
      .strict()
      .safeParse(await c.req.json().catch(() => null));
    if (!parsed.success)
      return c.json({ error: 'Bilinmeyen görev işlemi.' }, 400);
    if (parsed.data.action === 'run' && !store.settings().researchAllowed)
      return c.json({ error: 'Araştırma Ayarlar’da kapalı.' }, 403);
    const task = store.action(c.req.param('id'), parsed.data.action);
    if (parsed.data.action !== 'run') runner.abort(c.req.param('id'));
    return task ? c.json(task) : c.json({ error: 'Görev bulunamadı.' }, 404);
  });
  app.put('/api/tasks/:id/schedule', async (c) => {
    const parsed = z
      .object({ intervalSeconds: interval })
      .strict()
      .safeParse(await c.req.json().catch(() => null));
    if (!parsed.success)
      return c.json(
        {
          error:
            'Tekrar aralığı 60 saniye ile bir yıl arasında olmalı veya null olmalı.',
        },
        400,
      );
    const task = store.schedule(c.req.param('id'), parsed.data.intervalSeconds);
    return task ? c.json(task) : c.json({ error: 'Görev bulunamadı.' }, 404);
  });
  app.patch('/api/settings', async (c) => {
    const parsed = z
      .object({
        name: z.string().trim().min(1).max(40).optional(),
        paused: z.boolean().optional(),
        researchAllowed: z.boolean().optional(),
        memoryAllowed: z.boolean().optional(),
      })
      .strict()
      .safeParse(await c.req.json().catch(() => null));
    if (!parsed.success) return c.json({ error: 'Geçersiz ayarlar.' }, 400);
    const previous = store.settings();
    const settings = store.updateSettings(parsed.data);
    if (
      settings.paused ||
      !settings.researchAllowed ||
      previous.memoryAllowed !== settings.memoryAllowed
    )
      runner.abortAll();
    if (settings.paused) voice?.abortAll();
    else void voice?.resumePending();
    return c.json(settings);
  });
  app.post('/api/memories', async (c) => {
    const parsed = z
      .object({ text: z.string().trim().min(1).max(2000) })
      .strict()
      .safeParse(await c.req.json().catch(() => null));
    if (!parsed.success)
      return c.json(
        { error: 'Bellek 1 ile 2.000 karakter arasında olmalı.' },
        400,
      );
    return c.json(store.saveMemory(parsed.data.text), 201);
  });
  app.put('/api/memories/:id', async (c) => {
    const parsed = z
      .object({ text: z.string().trim().min(1).max(2000) })
      .strict()
      .safeParse(await c.req.json().catch(() => null));
    if (!parsed.success)
      return c.json(
        { error: 'Bellek 1 ile 2.000 karakter arasında olmalı.' },
        400,
      );
    if (!store.memories().some((m) => m.id === c.req.param('id')))
      return c.json({ error: 'Bellek bulunamadı.' }, 404);
    return c.json(store.saveMemory(parsed.data.text, c.req.param('id')));
  });
  app.delete('/api/memories/:id', (c) =>
    store.deleteMemory(c.req.param('id'))
      ? c.json({ ok: true })
      : c.json({ error: 'Bellek bulunamadı.' }, 404),
  );
  app.onError((error, c) => {
    console.error('API request failed:', error.name);
    return c.json(
      {
        error:
          'Sunucu bu isteği tamamlayamadı. Sunucu günlüklerini ve veritabanı erişimini kontrol et.',
      },
      500,
    );
  });
  return app;
}
