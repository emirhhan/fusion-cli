import { serve } from '@hono/node-server';
import type { Hono } from 'hono';
import type { Server } from 'node:http';

export interface Listener {
  port: number;
  close(): Promise<void>;
}

/** Yalnız 127.0.0.1'de, işletim sisteminin seçtiği rastgele portta dinler. */
export function listenLocal(app: Hono): Promise<Listener> {
  return new Promise((resolve, reject) => {
    const server = serve(
      { fetch: app.fetch, hostname: '127.0.0.1', port: 0 },
      (info) =>
        resolve({
          port: info.port,
          close: () => closeServer(server as Server),
        }),
    );
    server.once('error', reject);
  });
}

function closeServer(server: Server) {
  return new Promise<void>((resolve) => {
    server.close(() => resolve());
    server.closeAllConnections();
  });
}
