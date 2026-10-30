import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ProcessController } from "../processes/useProcesses";
import type { ProtocolClient } from "../protocol/client";
import { TestsPanel } from "./TestsPanel";

afterEach(cleanup);

function setup() {
  const request = vi.fn(async (name: string) =>
    name === "proje.komut_onerileri"
      ? { ok: true, komutlar: [{ tur: "test", ad: "Test", komut: "npm test" }] }
      : { ok: true, git: false, branch: null, degisen: 0, ileride: 0, geride: 0 });
  const client = { request } as unknown as ProtocolClient;
  const start = vi.fn(async () => undefined);
  const processes = { busy: false, processes: [], start } as unknown as ProcessController;
  render(<TestsPanel client={client} processes={processes} />);
  return { start, client, processes };
}

// U4-49b — Ölçüldü (30 Ekim): proje dosyalarından türeyen öneri komutlar (package.json betikleri)
// tek tıkla, hiçbir onay görmeden `surec.baslat` ile çalışıyordu.
describe("TestsPanel komut onayı (U4-49b)", () => {
  it("ilk çalıştırmada komutu gösterir ve onay verilmeden süreci başlatmaz", async () => {
    const { start } = setup();
    fireEvent.click(await screen.findByRole("button", { name: "Test" }));

    const card = await screen.findByRole("alertdialog", { name: "Komut onayı" });
    expect(card.textContent).toContain("npm test");
    expect(start).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Çalıştır" }));
    expect(start).toHaveBeenCalledWith("npm test");
    expect(screen.queryByRole("alertdialog")).toBeNull();
  });

  it("Vazgeç süreci başlatmaz; her tıklamada yeniden sorulur", async () => {
    const { start } = setup();
    fireEvent.click(await screen.findByRole("button", { name: "Test" }));
    fireEvent.click(screen.getByRole("button", { name: "Vazgeç" }));
    expect(start).not.toHaveBeenCalled();
    expect(screen.queryByRole("alertdialog")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Test" }));
    expect(screen.getByRole("alertdialog")).toBeTruthy();
  });

  it("\"Bu oturumda hep çalıştır\" sonraki tıklamalarda tekrar sormaz", async () => {
    const { start } = setup();
    fireEvent.click(await screen.findByRole("button", { name: "Test" }));
    fireEvent.click(screen.getByRole("button", { name: "Bu oturumda hep çalıştır" }));
    expect(start).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole("button", { name: "Test" }));
    expect(screen.queryByRole("alertdialog")).toBeNull();
    expect(start).toHaveBeenCalledTimes(2);
  });
});
