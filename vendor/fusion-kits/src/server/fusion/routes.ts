import { Hono } from 'hono';
import { z } from 'zod';
import type { FusionService } from './service.js';

export function fusionRoutes(service: FusionService) {
  const app = new Hono();
  app.get('/conversations/:id/fusion', (c) => {
    try {
      return c.json(service.snapshot(c.req.param('id')));
    } catch {
      return c.json(
        { error: 'Fusion sohbeti bu çalışma alanına ait değil.' },
        403,
      );
    }
  });
  app.post('/conversations/:id/fusion/reply', async (c) => {
    const parsed = z
      .object({
        runId: z.string().min(1).max(100),
        questionId: z.string().min(1).max(100),
        answer: z.union([
          z.object({ secim: z.enum(['once', 'session', 'deny']) }).strict(),
          z.object({ metin: z.string().trim().min(1).max(4000) }).strict(),
        ]),
      })
      .strict()
      .safeParse(await c.req.json().catch(() => null));
    if (!parsed.success)
      return c.json({ error: 'Fusion soru cevabı geçersiz.' }, 400);
    try {
      service.reply(
        c.req.param('id'),
        parsed.data.runId,
        parsed.data.questionId,
        parsed.data.answer,
      );
      return c.json({ ok: true });
    } catch (error) {
      return c.json(
        {
          error:
            error instanceof Error
              ? error.message
              : 'Fusion cevabı gönderilemedi.',
        },
        409,
      );
    }
  });
  app.post('/conversations/:id/fusion/cancel', async (c) => {
    const parsed = z
      .object({ runId: z.string().min(1).max(100) })
      .strict()
      .safeParse(await c.req.json().catch(() => null));
    if (!parsed.success)
      return c.json({ error: 'Fusion görev kimliği geçersiz.' }, 400);
    try {
      service.cancel(c.req.param('id'), parsed.data.runId);
      return c.json({ ok: true });
    } catch {
      return c.json({ error: 'Fusion görevi artık çalışmıyor.' }, 409);
    }
  });
  app.get('/fusion/projects', (c) =>
    c.json({
      configured: service.configured,
      projects: service.listProjects(),
    }),
  );
  app.post('/fusion/projects', async (c) => {
    const parsed = z
      .object({
        name: z.string().trim().min(1).max(64),
        path: z.string().trim().min(1).max(4096),
      })
      .strict()
      .safeParse(await c.req.json().catch(() => null));
    if (!parsed.success)
      return c.json({ error: 'Proje bilgisi geçersiz.' }, 400);
    try {
      return c.json(service.addProject(parsed.data.name, parsed.data.path));
    } catch (error) {
      return c.json(
        {
          error: error instanceof Error ? error.message : 'Proje eklenemedi.',
        },
        400,
      );
    }
  });
  app.delete('/fusion/projects/:name', (c) =>
    service.removeProject(c.req.param('name'))
      ? c.json({ ok: true })
      : c.json(
          { error: 'Proje bulunamadı ya da sunucu ayarından geliyor.' },
          404,
        ),
  );
  return app;
}
