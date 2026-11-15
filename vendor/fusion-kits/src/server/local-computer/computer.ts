import { mkdir, realpath } from 'node:fs/promises';
import { z } from 'zod';
import {
  computerInputs,
  type ComputerAction,
} from '../../shared/computer-types.js';
import { blankScreen } from './blank-screen.js';
import type { SessionState } from '../../shared/fusion-profile.js';
import type { KitBrowser } from './browser.js';
import { ControlState } from './control.js';
import { OperationError } from './errors.js';
import { runSandboxed } from './exec.js';
import { listFiles, readFileText, writeFileText } from './files.js';
import type { BrowserPool } from './pool.js';

type Input<A extends ComputerAction> = z.infer<(typeof computerInputs)[A]>;

function domainAllowed(host: string, domains: string[]) {
  const clean = host.replace(/^\./, '').toLowerCase();
  return domains.some((item) => {
    const allowed = item.replace(/^\./, '').toLowerCase();
    return clean === allowed || clean.endsWith(`.${allowed}`);
  });
}

/** Oturumu istenen alan adlarına daralt (çerezler ve localStorage kökenleri). */
export function scopeSession(
  state: SessionState,
  domains: string[],
): SessionState {
  return {
    cookies: state.cookies.filter((cookie) =>
      domainAllowed(cookie.domain, domains),
    ),
    origins: state.origins.filter((item) => {
      try {
        return domainAllowed(new URL(item.origin).hostname, domains);
      } catch {
        return false;
      }
    }),
  };
}

/** Tek bir Kit'in yerel bilgisayarı: klasör, (tembel) tarayıcı ve kontrol durumu. */
export class LocalComputer {
  readonly control = new ControlState();

  constructor(
    readonly id: string,
    private dirs: { files: string; profile: string },
    private dataDir: string,
    private pool: BrowserPool,
  ) {}

  async prepare() {
    await mkdir(this.dirs.files, { recursive: true });
    await mkdir(this.dirs.profile, { recursive: true });
  }

  async stop() {
    await this.pool.release(this.id);
  }

  private browser<T>(fn: (browser: KitBrowser) => Promise<T>) {
    return this.pool.use(this.id, this.dirs.profile, fn);
  }

  async handle(action: ComputerAction, raw: unknown): Promise<unknown> {
    const input = computerInputs[action].parse(raw) as Input<ComputerAction>;
    if (action === 'session_load' || action === 'session_clear')
      return this.sessionAction(action, input);
    if (action.startsWith('human_')) this.control.assertHumanMayAct();
    else if (this.isBrowser(action)) this.control.assertBotMayAct(action);
    if (action.startsWith('files_') || action === 'exec') {
      const root = await realpath(this.dirs.files);
      return this.fileAction(action, root, input);
    }
    if (action === 'screenshot') return this.screenshot();
    return this.browserAction(action, input);
  }

  /** Fusion oturumu (P-023): değerler yalnız tarayıcıya gider; yanıt yalnız sayı ve adlar. */
  private async sessionAction(action: ComputerAction, input: unknown) {
    if (action === 'session_clear') {
      await this.pool.release(this.id);
      return { cleared: true };
    }
    const body = input as Input<'session_load'>;
    // Fusion zaten süzer; yine de istenen alan adları dışındaki kayıt tarayıcıya girmez.
    const state = scopeSession(body.state, body.domains);
    await this.pool.load(this.id, this.dirs.profile, body.profile, state);
    return {
      loaded: true,
      profile: body.profile,
      domains: body.domains,
      cookies: state.cookies.length,
    };
  }

  private isBrowser(action: ComputerAction) {
    return !action.startsWith('files_') && action !== 'exec';
  }

  private async screenshot() {
    const open = this.pool.peek(this.id);
    // Panel dakikada birçok kez çeker; tarayıcıyı bunun için açma.
    if (!open) return blankScreen();
    try {
      return await open.screenshot();
    } catch (error) {
      if (this.pool.peek(this.id)) throw error;
      return blankScreen();
    }
  }

  private fileAction(action: ComputerAction, root: string, input: unknown) {
    switch (action) {
      case 'files_list':
        return listFiles(root, (input as Input<'files_list'>).path);
      case 'files_read':
        return readFileText(root, (input as Input<'files_read'>).path);
      case 'files_write': {
        const body = input as Input<'files_write'>;
        return writeFileText(root, body.path, body.contents, body.append);
      }
      case 'exec': {
        const body = input as Input<'exec'>;
        return runSandboxed(root, this.dataDir, body.command, body.timeoutMs);
      }
      default:
        throw new OperationError('Bilinmeyen bilgisayar işlemi.');
    }
  }

  private browserAction(action: ComputerAction, input: unknown) {
    return this.browser(async (b) => {
      switch (action) {
        case 'navigate':
          return b.navigate((input as Input<'navigate'>).url);
        case 'read':
          return b.read();
        case 'snapshot': {
          const snapshot = await b.snapshot();
          this.control.snapshotTaken();
          return snapshot;
        }
        case 'click': {
          const body = input as Input<'click'>;
          return b.click(body.ref, body.snapshotId);
        }
        case 'type': {
          const body = input as Input<'type'>;
          return b.type(body.ref, body.snapshotId, body.text, body.submit);
        }
        case 'key':
          return b.key((input as Input<'key'>).key);
        case 'scroll':
          return b.scroll((input as Input<'scroll'>).deltaY);
        case 'human_click': {
          const body = input as Input<'human_click'>;
          return b.humanClick(body.x, body.y);
        }
        case 'human_type':
          return b.humanType((input as Input<'human_type'>).text);
        case 'human_key':
          return b.humanKey((input as Input<'human_key'>).key);
        case 'human_scroll':
          return b.humanScroll((input as Input<'human_scroll'>).deltaY);
        default:
          throw new OperationError('Bilinmeyen bilgisayar işlemi.');
      }
    });
  }
}
