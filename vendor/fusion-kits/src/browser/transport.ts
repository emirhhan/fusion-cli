import http from 'node:http';
import https from 'node:https';
import { validateUrl } from './security.js';
// Browser networking is intercepted: each request is DNS-pinned to a validated
// public IP. Redirects are rejected before Playwright sees the Location header.
export async function readResource(
  input: string,
  signal?: AbortSignal,
): Promise<{ status: number; headers: Record<string, string>; body: Buffer }> {
  const { url, address, family } = await validateUrl(input);
  return new Promise((resolve, reject) => {
    const transport = url.protocol === 'https:' ? https : http;
    const request = transport.request(
      url,
      {
        method: 'GET',
        signal,
        headers: {
          'User-Agent': 'OpenDots/0.1 (read-only research)',
          Accept: 'text/html,image/*,text/css,*/*;q=0.5',
          'Accept-Encoding': 'identity',
        },
        lookup: (_hostname, options, callback) => {
          if (options.all) callback(null, [{ address, family }]);
          else callback(null, address, family);
        },
      },
      (response) => {
        if (
          response.statusCode &&
          response.statusCode >= 300 &&
          response.statusCode < 400
        ) {
          response.resume();
          reject(
            new Error(
              'Güvenlik için yönlendirmeler engellenir. Lütfen son kanonik sayfa adresini ver.',
            ),
          );
          return;
        }
        const chunks: Buffer[] = [];
        let size = 0;
        response.on('data', (chunk: Buffer) => {
          size += chunk.length;
          if (size > 5_000_000) {
            response.destroy(new Error('Kaynak 5 MB sınırını aşıyor.'));
          } else chunks.push(chunk);
        });
        response.on('error', reject);
        response.on('end', () => {
          const headers: Record<string, string> = {};
          for (const [key, value] of Object.entries(response.headers))
            if (
              value &&
              ![
                'set-cookie',
                'content-encoding',
                'transfer-encoding',
                'content-length',
                'location',
                'refresh',
              ].includes(key)
            )
              headers[key] = Array.isArray(value) ? value.join(', ') : value;
          resolve({
            status: response.statusCode ?? 502,
            headers,
            body: Buffer.concat(chunks),
          });
        });
      },
    );
    request.setTimeout(10_000, () =>
      request.destroy(new Error('Uzak kaynak zaman aşımına uğradı.')),
    );
    request.on('error', reject);
    request.end();
  });
}
