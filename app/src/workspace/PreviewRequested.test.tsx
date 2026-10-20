import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ProtocolClient } from "../protocol/client";
import { olayEkle } from "../protocol/olayAkisi";
import { PreviewCard } from "../screens/PreviewCard";
import { PreviewPanel } from "./PreviewPanel";

afterEach(cleanup);

/** Ölçüldü (2 Ekim): önizleme paneli vardı ama ajan ona adres veremiyordu. */
describe("Ajanın başlattığı önizleme", () => {
  it("PreviewReady sohbete tek kart olarak düşer, aynı adres çoğalmaz", () => {
    const olay = { olay: "PreviewReady", url: "http://127.0.0.1:8770/", kind: "wordpress", title: "Mağaza" };
    const bir = olayEkle([], olay);
    const iki = olayEkle(bir, olay);

    expect(iki.filter((m) => m.rol === "onizleme")).toHaveLength(1);
    expect(iki[0].onizleme).toEqual({ url: "http://127.0.0.1:8770/", baslik: "Mağaza", tur: "wordpress" });
  });

  it("kart uygulamada açma isteğini adresle iletir", () => {
    const onOpen = vi.fn();
    render(<PreviewCard baslik="Mağaza" onOpen={onOpen} tur="wordpress" url="http://127.0.0.1:8770/" />);

    expect(screen.getByRole("region", { name: "Önizleme hazır" }).textContent).toContain("WordPress");
    fireEvent.click(screen.getByRole("button", { name: "Uygulamada aç" }));
    expect(onOpen).toHaveBeenCalledWith("http://127.0.0.1:8770/");
  });

  it("panel istenen yerel adresi doğrulayıp web kipinde kendiliğinden açar", async () => {
    const client = {
      request: vi.fn(async (_name: string, data: { url: string }) => ({ ok: true, url: data.url })),
    } as unknown as ProtocolClient;

    render(
      <PreviewPanel client={client} requestedUrl={{ url: "http://127.0.0.1:8770/", seq: 1 }} selectedPath={null} />,
    );

    const cerceve = await screen.findByTitle("Yerel geliştirme önizlemesi");
    expect(cerceve.getAttribute("src")).toContain("http://127.0.0.1:8770/");
    await waitFor(() =>
      expect(client.request).toHaveBeenCalledWith("web.onizleme_dogrula", { url: "http://127.0.0.1:8770/" }),
    );
  });
});
