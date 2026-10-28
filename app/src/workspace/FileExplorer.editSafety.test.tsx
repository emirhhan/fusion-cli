import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import { ProtocolClient } from "../protocol/client";
import { FileExplorer } from "./FileExplorer";

afterEach(cleanup);

// Kesilmiş önizleme düzenlenip kaydedilirse dosyanın gösterilmeyen kısmı silinir.
function truncatedFileClient(calls: string[]) {
  let receive: ((line: string) => void) | null = null;
  return new ProtocolClient(
    (line) => {
      const request = JSON.parse(line) as { id: string; ad: string };
      calls.push(request.ad);
      const result =
        request.ad === "proje.durum"
          ? { ok: true }
          : request.ad === "proje.listele"
            ? { ok: true, girdiler: [{ ad: "buyuk.txt", yol: "buyuk.txt", tur: "dosya", boyut: 900000, degistirilme: 1 }] }
            : { ok: true, yol: "buyuk.txt", tur: "metin", mime: "text/plain", boyut: 900000, sha256: "tam", icerik: "ilk bölüm", kesildi: true };
      queueMicrotask(() => receive?.(JSON.stringify({ tip: "sonuc", id: request.id, veri: result })));
    },
    (handler) => {
      receive = handler;
    },
  );
}

it("kesilmiş dosyada düzenleme sunulmaz", async () => {
  const calls: string[] = [];
  render(<FileExplorer client={truncatedFileClient(calls)} root="/proje" />);
  fireEvent.click(await screen.findByRole("treeitem", { name: "buyuk.txt" }));

  expect(await screen.findByText(/kısmi içerik düzenlenemez/i)).toBeTruthy();
  expect(screen.queryByRole("button", { name: "Düzenle" })).toBeNull();
  expect(calls).not.toContain("proje.yaz");
});
