import { createHmac, timingSafeEqual } from 'node:crypto';
import { Hono } from 'hono';
import { z } from 'zod';
import { computerInputs } from '../../shared/computer-types.js';
import type { ComputerAction } from '../../shared/computer-types.js';
import type { LocalComputer } from './computer.js';
import { ConflictError, OperationError } from './errors.js';

/** ComputerService'in türettiği belirteç: HMAC-SHA256(computerToken, 'opendots-computer:' + id). */
export function computerBearer(computerToken: string, id: string) {
  return createHmac('sha256', computerToken)
    .update(`opendots-computer:${id}`)
    .digest('hex');
}

export function safeEqual(a: string, b: string) {
  const left = Buffer.from(a);
  const right = Buffer.from(b);
  return left.length === right.length && timingSafeEqual(left, right);
}

const GET_ACTIONS = new Set(['read', 'screenshot']);
const requestBody = z.object({ requestId: z.string().min(1).max(100) });

/** Bir Kit bilgisayarının HTTP yüzü; Bearer ve bot kimliği zorunlu. */
export function computerApp(computer: LocalComputer, computerToken: string) {
  const expected = computerBearer(computerToken, computer.id);
  const app = new Hono();
  app.onError((error, c) => {
    if (error instanceof ConflictError)
      return c.json({ error: error.message }, 409);
    if (error instanceof OperationError)
      return c.json({ error: error.message });
    if (error instanceof z.ZodError || error instanceof SyntaxError)
      return c.json({ error: 'Geçersiz bilgisayar isteği.' }, 400);
    console.error('Yerel bilgisayar hatası:', error);
    return c.json({ error: 'Bilgisayar işlemi başarısız oldu.' }, 500);
  });
  app.use('*', async (c, next) => {
    const bearer = (c.req.header('authorization') ?? '').replace(
      /^Bearer /,
      '',
    );
    if (
      !safeEqual(bearer, expected) ||
      c.req.header('x-openbot-bot-id') !== computer.id
    )
      return c.json({ error: 'Yetkisiz.' }, 401);
    await next();
  });
  app.get('/control', (c) => c.json(computer.control.view()));
  app.post('/control/request', (c) =>
    c.json(computer.control.requestControl()),
  );
  app.post('/control/take', async (c) =>
    c.json(
      computer.control.take(requestBody.parse(await c.req.json()).requestId),
    ),
  );
  app.post('/control/release', async (c) =>
    c.json(
      computer.control.release(requestBody.parse(await c.req.json()).requestId),
    ),
  );
  app.all('/*', async (c) => {
    const action = c.req.path.slice(1).replace('/', '_');
    if (!Object.hasOwn(computerInputs, action))
      return c.json({ error: 'Bulunamadı.' }, 404);
    const method = GET_ACTIONS.has(action) ? 'GET' : 'POST';
    if (c.req.method !== method)
      return c.json({ error: 'Yöntem desteklenmiyor.' }, 405);
    const input = method === 'GET' ? {} : await c.req.json();
    return c.json(await computer.handle(action as ComputerAction, input));
  });
  return app;
}
