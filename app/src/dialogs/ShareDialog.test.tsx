import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ShareDialog, shareableTranscript } from "./ShareDialog";

afterEach(cleanup);

describe("ShareDialog", () => {
  it("yalnız nihai sohbet metnini dışarı aktarır", () => {
    expect(shareableTranscript("Test", [
      { rol: "kullanici", metin: "Merhaba" },
      { rol: "olay", metin: "gizli işlem" },
      { rol: "asistan", metin: "Yazılıyor", akan: true },
      { rol: "asistan", metin: "Yanıt" },
      { rol: "degisiklik", metin: "/özel/dosya" },
    ])).toBe("# Test\n\n## Siz\n\nMerhaba\n\n## Fusion\n\nYanıt");
  });

  it("metni panoya kopyalar ve Escape ile kapanır", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
    const onClose = vi.fn();
    render(<ShareDialog messages={[{ rol: "asistan", metin: "Yanıt" }]} onClose={onClose} title="Sohbet" />);
    fireEvent.click(screen.getByRole("button", { name: "Metni kopyala" }));
    expect(writeText).toHaveBeenCalledWith("# Sohbet\n\n## Fusion\n\nYanıt");
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).toHaveBeenCalledOnce();
  });
});
