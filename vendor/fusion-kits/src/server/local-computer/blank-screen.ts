import { crc32, deflateSync } from 'node:zlib';
import { VIEWPORT } from './browser.js';

function chunk(type: string, data: Buffer) {
  const body = Buffer.concat([Buffer.from(type, 'ascii'), data]);
  const frame = Buffer.alloc(12 + data.length);
  frame.writeUInt32BE(data.length, 0);
  body.copy(frame, 4);
  frame.writeUInt32BE(crc32(body), 8 + data.length);
  return frame;
}

let cached: string | undefined;

/** Tarayıcı kapalıyken panelin göstereceği düz koyu görsel (tarayıcıyı açmadan). */
export function blankScreen() {
  const { width, height } = VIEWPORT;
  if (!cached) {
    const header = Buffer.alloc(13);
    header.writeUInt32BE(width, 0);
    header.writeUInt32BE(height, 4);
    header.set([8, 2, 0, 0, 0], 8); // 8 bit, RGB
    const row = Buffer.alloc(1 + width * 3, 0x1c);
    row[0] = 0;
    const png = Buffer.concat([
      Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
      chunk('IHDR', header),
      chunk('IDAT', deflateSync(Buffer.concat(Array(height).fill(row)))),
      chunk('IEND', Buffer.alloc(0)),
    ]);
    cached = png.toString('base64');
  }
  return {
    base64: cached,
    width,
    height,
    url: '',
    capturedAt: Date.now(),
    blank: true,
  };
}
