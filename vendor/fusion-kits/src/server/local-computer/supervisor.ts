import { join } from 'node:path';
import { Hono } from 'hono';
import { computerApp, safeEqual } from './app.js';
import { playwrightBrowserFactory, type BrowserFactory } from './browser.js';
import { LocalComputer } from './computer.js';
import { listenLocal, type Listener } from './listen.js';
import { BrowserPool, IDLE_CLOSE_MS } from './pool.js';

const ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$/;

export interface SupervisorOptions {
  /** Kit klasörlerinin kökü: <kök>/<kitId>/files ve <kök>/<kitId>/profile. */
  rootDir: string;
  supervisorToken: string;
  computerToken: string;
  namespace?: string;
  browserFactory?: BrowserFactory;
  idleMs?: number;
}

interface Running {
  computer: LocalComputer;
  listener: Listener;
}

/** Docker'sız yerel denetçi: ComputerService'in beklediği /computers API'sini sunar. */
export class LocalSupervisor {
  private running = new Map<string, Running>();
  private starting = new Map<string, Promise<Running>>();
  private pool: BrowserPool;
  private listener?: Listener;
  private namespace: string;

  constructor(private options: SupervisorOptions) {
    this.namespace = options.namespace || 'opendots';
    this.pool = new BrowserPool(
      options.browserFactory ?? playwrightBrowserFactory,
      options.idleMs ?? IDLE_CLOSE_MS,
    );
  }

  get url() {
    if (!this.listener) throw new Error('Yerel denetçi başlatılmadı.');
    return `http://127.0.0.1:${this.listener.port}`;
  }

  async start() {
    this.listener = await listenLocal(this.api());
    return this.url;
  }

  async close() {
    await Promise.all([...this.running.keys()].map((id) => this.stop(id)));
    await this.pool.close();
    await this.listener?.close();
    this.listener = undefined;
  }

  private state(id: string, status: 'running' | 'stopped', port?: number) {
    return {
      botId: id,
      container: `${this.namespace}-computer-${id}`,
      status,
      ...(port ? { port, url: `http://127.0.0.1:${port}` } : {}),
    };
  }

  list() {
    return [...this.running].map(([id, { listener }]) =>
      this.state(id, 'running', listener.port),
    );
  }

  /** Klasörü hazırlar ve kendi portunda dinleyiciyi açar; tarayıcıyı AÇMAZ. */
  async ensure(id: string) {
    const running = this.running.get(id);
    if (running) return this.state(id, 'running', running.listener.port);
    let start = this.starting.get(id);
    if (!start) {
      start = this.launch(id);
      this.starting.set(id, start);
      const forget = () => void this.starting.delete(id);
      start.then(forget, forget);
    }
    const started = await start;
    return this.state(id, 'running', started.listener.port);
  }

  private async launch(id: string): Promise<Running> {
    const base = join(this.options.rootDir, id);
    const computer = new LocalComputer(
      id,
      { files: join(base, 'files'), profile: join(base, 'profile') },
      this.options.rootDir,
      this.pool,
    );
    await computer.prepare();
    const listener = await listenLocal(
      computerApp(computer, this.options.computerToken),
    );
    const started = { computer, listener };
    this.running.set(id, started);
    return started;
  }

  async stop(id: string) {
    const running = this.running.get(id);
    this.running.delete(id);
    if (running) {
      await running.computer.stop();
      await running.listener.close();
    }
    return this.state(id, 'stopped');
  }

  private api() {
    const app = new Hono();
    app.use('*', async (c, next) => {
      const bearer = (c.req.header('authorization') ?? '').replace(
        /^Bearer /,
        '',
      );
      if (!safeEqual(bearer, this.options.supervisorToken))
        return c.json({ error: 'Yetkisiz.' }, 401);
      await next();
    });
    app.get('/computers', (c) => c.json({ computers: this.list() }));
    app.post('/computers/:id/ensure', async (c) => {
      const id = c.req.param('id');
      if (!ID_PATTERN.test(id))
        return c.json({ error: 'Geçersiz kimlik.' }, 400);
      return c.json(await this.ensure(id));
    });
    app.post('/computers/:id/stop', async (c) => {
      const id = c.req.param('id');
      if (!ID_PATTERN.test(id))
        return c.json({ error: 'Geçersiz kimlik.' }, 400);
      return c.json(await this.stop(id));
    });
    app.onError((error, c) => {
      console.error('Yerel denetçi hatası:', error);
      return c.json({ error: 'Denetçi işlemi başarısız oldu.' }, 500);
    });
    return app;
  }
}
