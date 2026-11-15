import { pageRoutes } from './page-routes.js';
import { ConversationRequestError } from './conversation-request-store.js';
import { isKitCharacter } from '../shared/characters.js';
import { Hono } from 'hono';
import { z } from 'zod';
import { Platform } from './platform.js';
import { VoiceService } from './voice.js';
import { ThreadBindingError } from './thread-restore.js';
import {
  learningContainerIdSchema,
  validateLearningSettings,
} from '../shared/learning.js';
const dotSchema = z
  .object({
    name: z.string().trim().min(1).max(40),
    instructions: z.string().trim().min(3).max(2000),
    researchAllowed: z.boolean(),
    memoryAllowed: z.boolean(),
    fusionAllowed: z.boolean().optional(),
    learningContainerId: learningContainerIdSchema.optional(),
    skillDeliveryEnabled: z.boolean().optional(),
    character: z.string().refine(isKitCharacter).optional(),
    spaceIds: z.array(z.string().min(1)).min(1).max(100).optional(),
    spaceId: z.string().min(1).optional(),
  })
  .strict();
export function workspaceRoutes(platform: Platform, voice: VoiceService) {
  const app = new Hono();
  app.route('/', pageRoutes(platform));
  app.get('/workspace', (c) =>
    c.json({
      ownerId: platform.workspace.ownerId,
      spaces: platform.workspace.spaces(),
      dots: platform.workspace.dots(),
      conversations: platform.workspace.conversations(),
      setup: platform.setup(),
      calls: platform.workspace.calls(),
      conversationRequestProtocol: 1,
    }),
  );
  app.post('/spaces', async (c) => {
    const data = z
      .object({
        name: z.string().trim().min(1).max(60),
        description: z.string().max(500).default(''),
      })
      .strict()
      .safeParse(await c.req.json());
    if (!data.success)
      return c.json({ error: 'Bir Alan adı gir (en fazla 60 karakter).' }, 400);
    return c.json(
      platform.workspace.createSpace(data.data.name, data.data.description),
      201,
    );
  });
  app.post('/dots', async (c) => {
    const data = dotSchema
      .extend({ spaceId: z.string() })
      .safeParse(await c.req.json());
    if (!data.success)
      return c.json(
        {
          error: 'Bir ad, rol yönergeleri ve açık araç izinleri belirt.',
        },
        400,
      );
    try {
      validateLearningSettings(
        data.data.learningContainerId ?? null,
        data.data.skillDeliveryEnabled ?? false,
      );
    } catch (error) {
      return c.json(
        {
          error:
            error instanceof Error
              ? error.message
              : 'Geçersiz Öğrenme ayarları.',
        },
        400,
      );
    }
    const created = platform.workspace.createDot(
      data.data.spaceId,
      data.data.name,
      data.data.instructions,
      data.data.researchAllowed,
      data.data.memoryAllowed,
      data.data.spaceIds,
      data.data.learningContainerId,
      data.data.skillDeliveryEnabled,
      data.data.character,
    );
    if (data.data.fusionAllowed !== undefined)
      platform.workspace.updateDot(created.id, {
        ...created,
        fusionAllowed: data.data.fusionAllowed,
      });
    return c.json(platform.workspace.dot(created.id), 201);
  });
  app.put('/dots/:id', async (c) => {
    const data = dotSchema.safeParse(await c.req.json());
    if (!data.success)
      return c.json({ error: 'Geçersiz uzman ayarları.' }, 400);
    const current = platform.workspace.dot(c.req.param('id'));
    if (!current) return c.json({ error: 'Kit bulunamadı.' }, 404);
    try {
      validateLearningSettings(
        data.data.learningContainerId === undefined
          ? (current.learningContainerId ?? null)
          : data.data.learningContainerId,
        data.data.skillDeliveryEnabled ?? current.skillDeliveryEnabled ?? false,
      );
    } catch (error) {
      return c.json(
        {
          error:
            error instanceof Error
              ? error.message
              : 'Geçersiz Öğrenme ayarları.',
        },
        400,
      );
    }
    return c.json(platform.workspace.updateDot(c.req.param('id'), data.data));
  });
  app.post('/conversations', async (c) => {
    const data = z
      .object({
        dotId: z.string(),
        title: z.string().trim().min(1).max(120).default('Yeni bir düşünce'),
        requestId: z
          .string()
          .regex(/^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$/)
          .optional(),
      })
      .strict()
      .safeParse(await c.req.json());
    if (!data.success)
      return c.json({ error: 'Bir Kit ve sohbet başlığı seç.' }, 400);
    try {
      const existing = data.data.requestId
        ? platform.workspace.conversationRequests.lookup(data.data.requestId)
        : null;
      if (!existing && platform.setup().missing.length)
        return c.json(
          { error: `Kurulum gerekli: ${platform.setup().missing.join(', ')}.` },
          503,
        );
      return c.json(
        await platform.createConversation(
          data.data.dotId,
          data.data.title,
          data.data.requestId,
        ),
        201,
      );
    } catch (error) {
      if (error instanceof ConversationRequestError)
        return c.json({ error: error.message }, error.status);
      return c.json(
        {
          error:
            'Sohbet kabulü doğrulanamadı; aynı isteğin durumunu kontrol et.',
        },
        503,
      );
    }
  });
  app.get('/conversations/requests/:requestId', (c) => {
    try {
      const receipt = platform.workspace.conversationRequests.lookup(
        c.req.param('requestId'),
      );
      if (!receipt)
        return c.json(
          { error: 'Bu kullanıcı kapsamında sohbet kabulü bulunamadı.' },
          404,
        );
      return c.json({
        requestId: receipt.requestId,
        threadId: receipt.threadId,
        state: receipt.state,
        conversation:
          receipt.state === 'completed'
            ? platform.workspace.requireThread(receipt.threadId, receipt.dotId)
            : null,
      });
    } catch (error) {
      if (error instanceof ConversationRequestError)
        return c.json({ error: error.message }, error.status);
      return c.json({ error: 'Sohbet kabul kaydı okunamadı.' }, 503);
    }
  });
  app.post('/conversations/import', async (c) => {
    const data = z
      .object({
        id: z
          .string()
          .min(1)
          .regex(/^[^\s/\\]+$/),
        dotId: z.string().min(1),
      })
      .strict()
      .safeParse(await c.req.json());
    if (!data.success)
      return c.json({ error: 'Sohbet ve Kit kimliği geçersiz.' }, 400);
    try {
      return c.json(
        await platform.importConversation(data.data.dotId, data.data.id),
      );
    } catch (error) {
      return c.json(
        {
          error:
            error instanceof ThreadBindingError
              ? error.message
              : 'Sohbet bağı kurulamadı.',
        },
        error instanceof ThreadBindingError ? error.status : 503,
      );
    }
  });
  app.get('/conversations/:id/capture', (c) =>
    c.json(platform.workspace.capture(c.req.param('id'))),
  );
  app.post('/voice/calls', async (c) => {
    const data = z
      .object({ threadId: z.string(), sdp: z.string().max(100000) })
      .strict()
      .safeParse(await c.req.json());
    if (!data.success)
      return c.json({ error: 'Bir sohbet ve ses SDP teklifi gerekli.' }, 400);
    return c.json(
      await voice.begin(data.data.threadId, data.data.sdp, c.req.raw.signal),
      201,
    );
  });
  app.post('/voice/calls/local', async (c) => {
    const data = z
      .object({ threadId: z.string() })
      .strict()
      .safeParse(await c.req.json());
    if (!data.success) return c.json({ error: 'Bir sohbet gerekli.' }, 400);
    return c.json(await voice.beginLocal(data.data.threadId), 201);
  });
  app.post('/voice/calls/:id/utterance', async (c) => {
    const data = z
      .object({ text: z.string().trim().min(1).max(4000) })
      .strict()
      .safeParse(await c.req.json());
    if (!data.success)
      return c.json({ error: 'Söylenen metin boş ya da çok uzun.' }, 400);
    return c.json({
      text: await voice.utterance(c.req.param('id'), data.data.text),
    });
  });
  app.get('/voice/calls/:id', (c) =>
    c.json(platform.workspace.call(c.req.param('id'))),
  );
  app.post('/voice/calls/:id/active', (c) =>
    c.json(voice.activate(c.req.param('id'))),
  );
  app.post('/voice/calls/:id/compute', async (c) => {
    const data = z
      .object({
        toolCallId: z.string().min(1).max(200),
        request: z.string().trim().min(1).max(4000),
        transcript: z.string().max(12000).default(''),
      })
      .strict()
      .safeParse(await c.req.json());
    if (!data.success)
      return c.json(
        { error: 'Sınırlı bir işlem isteği ve araç çağrısı kimliği gerekli.' },
        400,
      );
    return c.json({
      text: await voice.compute(
        c.req.param('id'),
        data.data.toolCallId,
        `${data.data.request}\n\nUntrusted current-call transcript for context:\n${data.data.transcript}`,
      ),
    });
  });
  app.post('/voice/calls/:id/end', async (c) => {
    const data = z
      .object({
        transcript: z.string().max(20000),
        anchorMessageId: z.string().max(200).optional(),
      })
      .strict()
      .safeParse(await c.req.json());
    if (!data.success)
      return c.json({ error: 'Döküm 20.000 karakter sınırını aşıyor.' }, 400);
    platform.workspace.anchorCall(c.req.param('id'), data.data.anchorMessageId);
    return c.json(await voice.end(c.req.param('id'), data.data.transcript));
  });
  app.all('/copilotkit/*', (c) => platform.handle(c.req.raw));
  app.onError((error, c) => {
    const text = error.message;
    // Kullanıcıya yazılmış (Türkçe) mesajlar gösterilir; kütüphanelerden gelen
    // İngilizce iç hatalar ayrıntı sızdırmamak için genel metne çevrilir.
    // Eski İngilizce önek listesi Türkçeleştirmeden sonra hiçbir mesajı
    // tanımıyordu ("önce mevcut aramayı bitir" bile gizleniyordu).
    const known =
      text.length <= 300 &&
      (/[çğıöşüÇĞİÖŞÜ]/.test(text) ||
        /^(Setup|Voice setup|Dot |Space |Specialist |Conversation |Call |This call|End the current|Voice provider|An audio|Intelligence could not)/.test(
          text,
        ));
    return c.json(
      {
        error: known
          ? text
          : 'Hizmet isteği başarısız oldu. Sunucu yapılandırmasını kontrol edip yeniden dene.',
      },
      503,
    );
  });
  return app;
}
