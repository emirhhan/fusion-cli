import { describe, expect, it } from "vitest";
import {
  DEFAULT_VIEWPORT_ID,
  DESKTOP_SCREENSHOT_WIDTH,
  PREVIEW_VIEWPORTS,
  findViewport,
  frameWidth,
  screenshotSize,
} from "./previewViewports";

describe("önizleme cihaz boyutları (P-041)", () => {
  it("320/375/768/1024/1440 kırılımlarını ve masaüstünü tek listede tutar", () => {
    expect(PREVIEW_VIEWPORTS.map((item) => item.width)).toEqual([null, 1440, 1024, 768, 375, 320]);
    expect(new Set(PREVIEW_VIEWPORTS.map((item) => item.id)).size).toBe(PREVIEW_VIEWPORTS.length);
    expect(DEFAULT_VIEWPORT_ID).toBe("desktop");
  });

  it("bilinmeyen kimlik masaüstüne düşer; iframe genişliği ve görüntü ölçüsü listeden gelir", () => {
    expect(findViewport("yok").id).toBe("desktop");
    expect(frameWidth(findViewport("desktop"))).toBe("100%");
    expect(frameWidth(findViewport("mobile"))).toBe("375px");
    expect(screenshotSize(findViewport("desktop"))).toEqual({ genislik: DESKTOP_SCREENSHOT_WIDTH, yukseklik: 800 });
    expect(screenshotSize(findViewport("tablet"))).toEqual({ genislik: 768, yukseklik: 1024 });
  });
});
