import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { inflateSync } from "node:zlib";
import { describe, expect, it } from "vitest";

const ASSETS = ["approval", "blink", "happy", "idle", "talking-a", "talking-b", "thinking"] as const;
const CANVAS_SIZE = 1_600;
const SAFE_PADDING = 192;
const BASELINE = CANVAS_SIZE - SAFE_PADDING;

type PngGeometry = {
  bbox: [number, number, number, number];
  colorType: number;
  height: number;
  width: number;
};

function paeth(left: number, above: number, upperLeft: number): number {
  const estimate = left + above - upperLeft;
  const leftDistance = Math.abs(estimate - left);
  const aboveDistance = Math.abs(estimate - above);
  const upperLeftDistance = Math.abs(estimate - upperLeft);
  if (leftDistance <= aboveDistance && leftDistance <= upperLeftDistance) return left;
  return aboveDistance <= upperLeftDistance ? above : upperLeft;
}

function readGeometry(name: (typeof ASSETS)[number]): PngGeometry {
  const png = readFileSync(resolve(process.cwd(), "src", "brand", "character", `${name}.png`));
  expect(png.subarray(0, 8).toString("hex")).toBe("89504e470d0a1a0a");

  let offset = 8;
  let width = 0;
  let height = 0;
  let colorType = 0;
  const imageData: Buffer[] = [];
  while (offset < png.length) {
    const length = png.readUInt32BE(offset);
    const type = png.subarray(offset + 4, offset + 8).toString("ascii");
    const data = png.subarray(offset + 8, offset + 8 + length);
    if (type === "IHDR") {
      width = data.readUInt32BE(0);
      height = data.readUInt32BE(4);
      expect(data[8]).toBe(8);
      colorType = data[9];
      expect(data[12]).toBe(0);
    } else if (type === "IDAT") {
      imageData.push(data);
    } else if (type === "IEND") {
      break;
    }
    offset += length + 12;
  }

  expect(colorType).toBe(6);
  const bytesPerPixel = 4;
  const stride = width * bytesPerPixel;
  const filtered = inflateSync(Buffer.concat(imageData));
  const pixels = Buffer.alloc(stride * height);

  for (let y = 0; y < height; y += 1) {
    const rowStart = y * (stride + 1);
    const outputStart = y * stride;
    const previousStart = outputStart - stride;
    const filter = filtered[rowStart];
    for (let x = 0; x < stride; x += 1) {
      const value = filtered[rowStart + x + 1];
      const left = x >= bytesPerPixel ? pixels[outputStart + x - bytesPerPixel] : 0;
      const above = y > 0 ? pixels[previousStart + x] : 0;
      const upperLeft = y > 0 && x >= bytesPerPixel ? pixels[previousStart + x - bytesPerPixel] : 0;
      const predictor =
        filter === 0 ? 0
        : filter === 1 ? left
        : filter === 2 ? above
        : filter === 3 ? Math.floor((left + above) / 2)
        : filter === 4 ? paeth(left, above, upperLeft)
        : Number.NaN;
      if (Number.isNaN(predictor)) throw new Error(`${name}.png: unsupported PNG filter ${filter}`);
      pixels[outputStart + x] = (value + predictor) & 0xff;
    }
  }

  let left = width;
  let top = height;
  let right = 0;
  let bottom = 0;
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      if (pixels[(y * width + x) * bytesPerPixel + 3] === 0) continue;
      left = Math.min(left, x);
      top = Math.min(top, y);
      right = Math.max(right, x + 1);
      bottom = Math.max(bottom, y + 1);
    }
  }

  return { bbox: [left, top, right, bottom], colorType, height, width };
}

describe("Fusion character asset geometry", () => {
  it.each(ASSETS)("%s.png ortak tuval, merkez, taban ve güvenlik boşluğunu korur", (name) => {
    const { bbox, colorType, height, width } = readGeometry(name);
    const [left, top, right, bottom] = bbox;

    expect({ width, height, colorType }).toEqual({ width: CANVAS_SIZE, height: CANVAS_SIZE, colorType: 6 });
    expect(Math.min(left, top, width - right, height - bottom)).toBeGreaterThanOrEqual(SAFE_PADDING);
    expect((left + right) / 2).toBe(CANVAS_SIZE / 2);
    expect(bottom).toBe(BASELINE);
  });
});
