import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { ProtocolClient } from "../protocol/client";
import { FileExplorer } from "./FileExplorer";

afterEach(cleanup);

function workspaceClient(
  respond: (name: string, data: Record<string, unknown>) => Record<string, unknown>,
) {
  let receive: ((line: string) => void) | null = null;
  return new ProtocolClient(
    (line) => {
      const request = JSON.parse(line) as {
        id: string;
        ad: string;
        veri: Record<string, unknown>;
      };
      const result = respond(request.ad, request.veri);
      queueMicrotask(() => receive?.(JSON.stringify({ tip: "sonuc", id: request.id, veri: result })));
    },
    (handler) => {
      receive = handler;
    },
  );
}

it("binary dosyayı bozuk metin yerine güvenli açıklamayla gösterir", async () => {
  const client = workspaceClient((name) => {
    if (name === "proje.durum") return { ok: true };
    if (name === "proje.listele") {
      return {
        ok: true,
        girdiler: [{ ad: "logo.png", yol: "logo.png", tur: "dosya", boyut: 42, degistirilme: 1 }],
      };
    }
    return {
      ok: true,
      yol: "logo.png",
      tur: "binary",
      mime: "image/png",
      boyut: 42,
      sha256: "abc",
      icerik: null,
      kesildi: false,
    };
  });

  render(<FileExplorer client={client} root="/proje" />);
  fireEvent.click(await screen.findByRole("treeitem", { name: "logo.png" }));

  expect(await screen.findByText(/bu dosya metin değil/i)).toBeTruthy();
  expect(screen.queryByText("null")).toBeNull();
});

it("geçersiz protokol cevabını boş ağaç gibi gizlemez", async () => {
  const client = workspaceClient((name) =>
    name === "proje.durum" ? { ok: true } : { ok: false, metin: "Proje okunamadı." },
  );

  render(<FileExplorer client={client} root="/proje" />);

  expect(await screen.findByRole("alert")).toHaveProperty("textContent", "Error: Proje okunamadı.");
});

it("ok tuşuyla görünür dosyalar arasında klavye odağını taşır", async () => {
  const client = workspaceClient((name) => {
    if (name === "proje.durum") return { ok: true };
    return {
      ok: true,
      girdiler: [
        { ad: "a.txt", yol: "a.txt", tur: "dosya", boyut: 1, degistirilme: 1 },
        { ad: "b.txt", yol: "b.txt", tur: "dosya", boyut: 1, degistirilme: 1 },
      ],
    };
  });

  render(<FileExplorer client={client} root="/proje" />);
  const first = await screen.findByRole("treeitem", { name: "a.txt" });
  const second = screen.getByRole("treeitem", { name: "b.txt" });
  first.focus();
  fireEvent.keyDown(first, { key: "ArrowDown" });

  expect(document.activeElement).toBe(second);
});

it("metin dosyasını seçilebilir satır numaralarıyla gösterir", async () => {
  const client = workspaceClient((name) => {
    if (name === "proje.durum") return { ok: true };
    if (name === "proje.listele") {
      return {
        ok: true,
        girdiler: [{ ad: "code.txt", yol: "code.txt", tur: "dosya", boyut: 7, degistirilme: 1 }],
      };
    }
    return {
      ok: true,
      yol: "code.txt",
      tur: "metin",
      mime: "text/plain",
      boyut: 7,
      sha256: "abc",
      icerik: "one\ntwo",
      kesildi: false,
    };
  });

  render(<FileExplorer client={client} root="/proje" />);
  fireEvent.click(await screen.findByRole("treeitem", { name: "code.txt" }));

  expect(await screen.findByText("one")).toBeTruthy();
  expect(screen.getByText("1", { selector: ".file-explorer__line-number" })).toBeTruthy();
  expect(screen.getByText("2", { selector: ".file-explorer__line-number" })).toBeTruthy();
});

it('dosya revizyonu açık klasörü ve kaydedilmemiş editörü koruyarak listeyi yeniler', async () => {
  let added = false;
  const client = workspaceClient((name, data) => {
    if (name === 'proje.durum') return { ok: true };
    if (name === 'proje.oku') return { ok: true, yol: 'src/a.txt', tur: 'metin', mime: 'text/plain', boyut: 4, sha256: 'base', icerik: 'base', kesildi: false };
    return { ok: true, girdiler: data.yol === ''
      ? [{ ad: 'src', yol: 'src', tur: 'klasor', boyut: 0, degistirilme: 0 }]
      : [{ ad: 'a.txt', yol: 'src/a.txt', tur: 'dosya', boyut: 4, degistirilme: 0 }, ...(added ? [{ ad: 'new.txt', yol: 'src/new.txt', tur: 'dosya', boyut: 1, degistirilme: 1 }] : [])] };
  });
  const { rerender } = render(<FileExplorer client={client} root='/project' revision={0} />);
  fireEvent.click(await screen.findByRole('treeitem', { name: 'src' }));
  fireEvent.click(await screen.findByRole('treeitem', { name: 'a.txt' }));
  fireEvent.click(await screen.findByRole('button', { name: 'Düzenle' }));
  fireEvent.change(screen.getByLabelText('Dosya içeriği'), { target: { value: 'Unsaved edit' } });
  added = true;
  rerender(<FileExplorer client={client} root='/project' revision={1} />);
  await screen.findByRole('treeitem', { name: 'new.txt' });
  expect((screen.getByLabelText('Dosya içeriği') as HTMLTextAreaElement).value).toBe('Unsaved edit');
  expect(screen.getByRole('treeitem', { name: 'src' }).getAttribute('aria-expanded')).toBe('true');
});

// U4-02 — Ölçüldü (29 Ekim): tek bir dosya okuma hatası `state.error` set edip ağacın TAMAMINI
// hata satırıyla değiştiriyordu; kullanıcı başka dosya seçemiyordu.
it("dosya okuma hatası ağacı gizlemez, hatayı görüntüleyicide gösterir", async () => {
  const client = workspaceClient((name, data) => {
    if (name === "proje.durum") return { ok: true };
    if (name === "proje.oku") {
      return data.yol === "kotu.bin"
        ? { ok: false, metin: "Dosya çok büyük." }
        : { ok: true, yol: "iyi.txt", tur: "metin", mime: "text/plain", boyut: 3, sha256: "x", icerik: "iyi", kesildi: false };
    }
    return { ok: true, girdiler: [
      { ad: "kotu.bin", yol: "kotu.bin", tur: "dosya", boyut: 1, degistirilme: 1 },
      { ad: "iyi.txt", yol: "iyi.txt", tur: "dosya", boyut: 3, degistirilme: 1 },
    ] };
  });
  render(<FileExplorer client={client} root="/proje" />);
  fireEvent.click(await screen.findByRole("treeitem", { name: "kotu.bin" }));
  expect((await screen.findByRole("alert")).textContent).toContain("Dosya çok büyük.");
  expect(screen.getByRole("treeitem", { name: "iyi.txt" })).toBeTruthy();
  fireEvent.click(screen.getByRole("treeitem", { name: "iyi.txt" }));
  expect(await screen.findByText("iyi")).toBeTruthy();
  expect(screen.queryByRole("alert")).toBeNull();
});

it("klasör açma hatası ağacı gizlemez", async () => {
  const client = workspaceClient((name, data) => {
    if (name === "proje.durum") return { ok: true };
    if (data.yol === "") return { ok: true, girdiler: [
      { ad: "src", yol: "src", tur: "klasor", boyut: 0, degistirilme: 0 },
      { ad: "a.txt", yol: "a.txt", tur: "dosya", boyut: 1, degistirilme: 1 },
    ] };
    return { ok: false, metin: "İzin yok." };
  });
  render(<FileExplorer client={client} root="/proje" />);
  fireEvent.click(await screen.findByRole("treeitem", { name: "src" }));
  expect((await screen.findByRole("alert")).textContent).toContain("İzin yok.");
  expect(screen.getByRole("treeitem", { name: "a.txt" })).toBeTruthy();
});

// Ölçüldü (30 Ekim): tek 200'lük sayfa okunuyordu, kalan dosyalar görünmüyordu (U4-42); CRLF'li dosya
// kaydedilince LF'ye dönüyordu (U4-44).
it("200'den fazla girdili dizinin bütün sayfaları okunur (U4-42)", async () => {
  const tum = Array.from({ length: 250 }, (_, i) => ({ ad: `f${String(i).padStart(3, "0")}.txt`, yol: `f${i}.txt`, tur: "dosya", boyut: 1, degistirilme: 1 }));
  const client = workspaceClient((name, data) => {
    if (name === "proje.durum") return { ok: true };
    const cursor = Number(data.cursor ?? 0);
    const sayfa = tum.slice(cursor, cursor + 200);
    const sonraki = cursor + sayfa.length;
    return { ok: true, girdiler: sayfa, next_cursor: sonraki < tum.length ? sonraki : null, has_more: sonraki < tum.length };
  });
  render(<FileExplorer client={client} root="/proje" />);
  expect(await screen.findByRole("treeitem", { name: "f249.txt" })).toBeTruthy();
  expect(screen.getAllByRole("treeitem")).toHaveLength(250);
});

it("CRLF'li dosya düzenlenip kaydedilince satır sonları korunur ve görünüm değişse bile onChanged çağrılır (U4-44)", async () => {
  const yazilan: string[] = [];
  const client = workspaceClient((name, data) => {
    if (name === "proje.durum") return { ok: true };
    if (name === "proje.listele") return { ok: true, girdiler: [{ ad: "a.txt", yol: "a.txt", tur: "dosya", boyut: 4, degistirilme: 1 }] };
    if (name === "proje.yaz") { yazilan.push(String(data.icerik)); return { ok: true, sha256: "yeni" }; }
    return { ok: true, yol: "a.txt", tur: "metin", mime: "text/plain", boyut: 6, sha256: "eski", icerik: "bir\r\niki", kesildi: false };
  });
  const onChanged = vi.fn();
  render(<FileExplorer client={client} onChanged={onChanged} root="/proje" />);
  fireEvent.click(await screen.findByRole("treeitem", { name: "a.txt" }));
  fireEvent.click(await screen.findByRole("button", { name: "Düzenle" }));
  fireEvent.change(screen.getByLabelText("Dosya içeriği"), { target: { value: "bir\nüç" } });
  fireEvent.click(screen.getByRole("button", { name: "Kaydet" }));
  await waitFor(() => expect(onChanged).toHaveBeenCalled());
  expect(yazilan).toEqual(["bir\r\nüç"]);
});
