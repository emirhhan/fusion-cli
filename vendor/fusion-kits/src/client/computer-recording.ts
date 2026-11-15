/**
 * Kit bilgisayarı canlı izleme ve GIF kaydı (P-044).
 *
 * Claude in Chrome `gif_creator` ve Fusion'ın Chrome `record` komutunun Kits karşılığı. Kare
 * kaynağı tektir: panelin çektiği ekran kareleri (`GET /dots/:id/computer/frame`). Canlı
 * izlemede kareler saniyede bir çekilir; kayıt açıkken aynı kareler biriktirilir ve durdurunca
 * tarayıcıda GIF'e çevrilir — sunucuya ek yük, bağımlılık ya da WASM yoktur.
 *
 * GIF kodlayıcı bilinçli olarak küçüktür: sabit 6×6×6 renk küpü (216 renk) ve standart LZW.
 * Ekran kaydında fotoğraf kalitesi değil okunabilirlik önemlidir; palet tahmini kare başına
 * işlem maliyetini sabit tutar.
 */

/** Canlı izlemede kare aralığı. */
export const LIVE_INTERVAL_MS = 1000;
/** Olağan (canlı olmayan) yenileme aralığı. */
export const IDLE_INTERVAL_MS = 4000;
/** Bir kayıtta en fazla kare (~2,5 dk @ 1 kare/sn); dolunca kayıt kendiliğinden durur. */
export const MAX_RECORDING_FRAMES = 150;
/** GIF'te kare genişliği tavanı (Fusion Chrome kaydıyla aynı: 960 px). */
export const MAX_GIF_WIDTH = 960;
/** Kare süresinin sınırları (1/100 sn). */
const MIN_DELAY_CS = 10;
const MAX_DELAY_CS = 300;

export function pollDelay(live: boolean): number {
  return live ? LIVE_INTERVAL_MS : IDLE_INTERVAL_MS;
}

export type RecordedFrame = { base64: string; capturedAt: number };

/** Kayıt sırasında kareleri biriktirir; aynı ana ait kare iki kez eklenmez. */
export class FrameRecorder {
  private frames: RecordedFrame[] = [];
  add(frame: RecordedFrame): boolean {
    if (this.full) return false;
    const last = this.frames.at(-1);
    if (last && last.capturedAt === frame.capturedAt) return false;
    this.frames.push({ base64: frame.base64, capturedAt: frame.capturedAt });
    return true;
  }
  get full(): boolean {
    return this.frames.length >= MAX_RECORDING_FRAMES;
  }
  get count(): number {
    return this.frames.length;
  }
  take(): RecordedFrame[] {
    const frames = this.frames;
    this.frames = [];
    return frames;
  }
}

/** Ardışık çekim anlarından kare süreleri (1/100 sn); son kare bir öncekinin süresini alır. */
export function frameDelays(frames: RecordedFrame[]): number[] {
  return frames.map((frame, index) => {
    const next = frames[index + 1] ?? frame;
    const previous = frames[index - 1] ?? frame;
    const gap =
      next === frame
        ? frame.capturedAt - previous.capturedAt
        : next.capturedAt - frame.capturedAt;
    const cs = Math.round((gap || LIVE_INTERVAL_MS) / 10);
    return Math.min(MAX_DELAY_CS, Math.max(MIN_DELAY_CS, cs));
  });
}

export type RgbaFrame = {
  width: number;
  height: number;
  rgba: Uint8ClampedArray;
};

/**
 * Akışlı GIF89a kodlayıcı: her kare eklendiği anda kodlanır, yalnız sıkıştırılmış baytlar
 * tutulur.
 *
 * Ölçüldü (31 Ekim, bağımsız inceleme): ilk sürüm 150 kareyi birden RGBA olarak çözüp
 * bellekte tutuyordu (960×600×4 B × 150 ≈ 350 MB) ve çıktıyı 8 baytlık `number[]` ile
 * biriktiriyordu; dolu bir kayıt durdurulunca sekme donabiliyordu. Artık aynı anda bellekte
 * yalnız bir karenin pikselleri bulunur.
 */
export class GifEncoder {
  private out = new ByteWriter();
  private frames = 0;
  constructor(
    readonly width: number,
    readonly height: number,
  ) {
    this.out.text('GIF89a');
    this.out.u16(width);
    this.out.u16(height);
    this.out.bytes([0xf7, 0, 0]); // genel renk tablosu: 256 renk
    this.out.bytes(PALETTE);
    // NETSCAPE2.0: sonsuz döngü.
    this.out.bytes([0x21, 0xff, 0x0b]);
    this.out.text('NETSCAPE2.0');
    this.out.bytes([0x03, 0x01, 0x00, 0x00, 0x00]);
  }
  addFrame(frame: RgbaFrame, delayCs: number = MIN_DELAY_CS): void {
    const out = this.out;
    out.bytes([0x21, 0xf9, 0x04, 0x00]);
    out.u16(delayCs);
    out.bytes([0x00, 0x00]);
    out.bytes([0x2c]);
    out.u16(0);
    out.u16(0);
    out.u16(frame.width);
    out.u16(frame.height);
    out.bytes([0x00]);
    out.bytes([8]); // LZW en küçük kod boyu
    const data = lzwEncode(quantize(frame.rgba), 8);
    for (let offset = 0; offset < data.length; offset += 255) {
      const block = data.subarray(offset, offset + 255);
      out.bytes([block.length]);
      out.bytes(block);
    }
    out.bytes([0x00]);
    this.frames++;
  }
  finish(): Uint8Array {
    if (this.frames === 0) throw new Error('Kayıtta kare yok.');
    this.out.bytes([0x3b]);
    return this.out.result();
  }
}

/** RGBA kareleri tek animasyonlu GIF89a'ya kodla (sonsuz döngü). */
export function encodeGif(frames: RgbaFrame[], delaysCs: number[]): Uint8Array {
  if (frames.length === 0) throw new Error('Kayıtta kare yok.');
  const encoder = new GifEncoder(
    Math.max(...frames.map((frame) => frame.width)),
    Math.max(...frames.map((frame) => frame.height)),
  );
  frames.forEach((frame, index) =>
    encoder.addFrame(frame, delaysCs[index] ?? MIN_DELAY_CS),
  );
  return encoder.finish();
}

/** 6×6×6 renk küpü + siyah dolgu (256 renk, RGB üçlüleri). */
const PALETTE: number[] = (() => {
  const colors: number[] = [];
  for (let r = 0; r < 6; r++)
    for (let g = 0; g < 6; g++)
      for (let b = 0; b < 6; b++) colors.push(r * 51, g * 51, b * 51);
  while (colors.length < 256 * 3) colors.push(0, 0, 0);
  return colors;
})();

export function quantize(rgba: Uint8ClampedArray): Uint8Array {
  const indices = new Uint8Array(rgba.length / 4);
  for (let pixel = 0; pixel < indices.length; pixel++) {
    const r = Math.round(rgba[pixel * 4] / 51);
    const g = Math.round(rgba[pixel * 4 + 1] / 51);
    const b = Math.round(rgba[pixel * 4 + 2] / 51);
    indices[pixel] = r * 36 + g * 6 + b;
  }
  return indices;
}

/** GIF değişken boylu LZW (bitler düşük anlamlıdan başlar). */
export function lzwEncode(
  indices: Uint8Array,
  minCodeSize: number,
): Uint8Array {
  const clear = 1 << minCodeSize;
  const end = clear + 1;
  const out = new ByteWriter(indices.length >> 1);
  let buffer = 0;
  let bits = 0;
  let codeSize = minCodeSize + 1;
  let next = end + 1;
  let table = new Map<number, number>();
  const emit = (code: number) => {
    buffer |= code << bits;
    bits += codeSize;
    while (bits >= 8) {
      out.byte(buffer & 0xff);
      buffer >>>= 8;
      bits -= 8;
    }
  };
  emit(clear);
  if (indices.length === 0) {
    emit(end);
    if (bits > 0) out.byte(buffer & 0xff);
    return out.result();
  }
  let prefix = indices[0];
  for (let index = 1; index < indices.length; index++) {
    const symbol = indices[index];
    const key = (prefix << 8) | symbol;
    const known = table.get(key);
    if (known !== undefined) {
      prefix = known;
      continue;
    }
    emit(prefix);
    if (next < 4096) {
      table.set(key, next++);
      if (next > 1 << codeSize && codeSize < 12) codeSize++;
    } else {
      emit(clear);
      table = new Map();
      codeSize = minCodeSize + 1;
      next = end + 1;
    }
    prefix = symbol;
  }
  emit(prefix);
  emit(end);
  if (bits > 0) out.byte(buffer & 0xff);
  return out.result();
}

/** Büyüyen bayt tamponu (`number[]` yerine: bayt başına 8 değil 1 bayt). */
class ByteWriter {
  private buffer: Uint8Array;
  private length = 0;
  constructor(capacity = 1 << 16) {
    this.buffer = new Uint8Array(Math.max(16, capacity));
  }
  private reserve(extra: number) {
    if (this.length + extra <= this.buffer.length) return;
    let size = this.buffer.length * 2;
    while (size < this.length + extra) size *= 2;
    const grown = new Uint8Array(size);
    grown.set(this.buffer.subarray(0, this.length));
    this.buffer = grown;
  }
  byte(value: number) {
    this.reserve(1);
    this.buffer[this.length++] = value;
  }
  bytes(values: ArrayLike<number>) {
    this.reserve(values.length);
    for (let index = 0; index < values.length; index++)
      this.buffer[this.length++] = values[index];
  }
  u16(value: number) {
    this.byte(value & 0xff);
    this.byte((value >> 8) & 0xff);
  }
  text(value: string) {
    for (const char of value) this.byte(char.charCodeAt(0));
  }
  result(): Uint8Array {
    return this.buffer.slice(0, this.length);
  }
}

/**
 * Tarayıcıda: PNG karelerini sırayla çöz, ilk karenin boyutuna (en çok 960 px) ölçekle ve
 * hemen kodla. Aynı anda yalnız bir karenin pikselleri bellektedir.
 */
export async function framesToGif(frames: RecordedFrame[]): Promise<Blob> {
  if (frames.length === 0) throw new Error('Kayıtta kare yok.');
  const delays = frameDelays(frames);
  const canvas = document.createElement('canvas');
  const context = canvas.getContext('2d');
  if (!context) throw new Error('Tarayıcı kareleri çizemedi (canvas yok).');
  let encoder: GifEncoder | null = null;
  for (const [index, frame] of frames.entries()) {
    const response = await fetch(`data:image/png;base64,${frame.base64}`);
    const bitmap = await createImageBitmap(await response.blob());
    if (!encoder) {
      const scale = Math.min(1, MAX_GIF_WIDTH / bitmap.width);
      canvas.width = Math.max(1, Math.round(bitmap.width * scale));
      canvas.height = Math.max(1, Math.round(bitmap.height * scale));
      encoder = new GifEncoder(canvas.width, canvas.height);
    }
    context.clearRect(0, 0, canvas.width, canvas.height);
    context.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    bitmap.close();
    encoder.addFrame(
      {
        width: canvas.width,
        height: canvas.height,
        rgba: context.getImageData(0, 0, canvas.width, canvas.height).data,
      },
      delays[index],
    );
  }
  if (!encoder) throw new Error('Kayıtta kare yok.');
  const bytes = encoder.finish();
  return new Blob([bytes.slice().buffer], { type: 'image/gif' });
}
