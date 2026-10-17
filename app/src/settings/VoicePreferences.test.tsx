import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ProtocolClient } from "../protocol/client";
import { VoicePreferences } from "./VoicePreferences";

afterEach(cleanup);

function voiceClient(options: { installed?: boolean } = {}) {
  const state = { hiz: 1 };
  return {
    onEvent: vi.fn(() => () => undefined),
    request: vi.fn(async (name: string, data: Record<string, unknown>) => {
      if (name === "ses.durum") {
        return {
          ok: true,
          ayar: { ...state },
          kullanilabilir: true,
          model_kurulu: options.installed ?? false,
          motor: options.installed ? "ema" : "sistem",
          ses: options.installed ? "EMA Lightning" : "Cem",
          turkce: true,
          yukseltme: null,
        };
      }
      if (name === "ses.ayar") {
        Object.assign(state, data);
        return { ok: true, ...state };
      }
      return { ok: false, metin: "Bilinmeyen istek" };
    }),
  } as unknown as ProtocolClient;
}

describe("VoicePreferences", () => {
  it("gerçek motoru ve kayıtlı ses tercihlerini gösterir", async () => {
    render(<VoicePreferences client={voiceClient({ installed: true })} />);

    expect(await screen.findByText("EMA Lightning · EMA Lightning")).toBeTruthy();
    expect(screen.getByText("1.00×")).toBeTruthy();
    expect(screen.queryByLabelText("Robotik")).toBeNull();
  });

  it("değiştirilen hızı çekirdeğe kaydedip ekranda korur", async () => {
    const client = voiceClient();
    render(<VoicePreferences client={client} />);
    const speed = await screen.findByLabelText("Hız");

    // `range` gerçek tarayıcıda `input` üretir; `change` jsdom/WebKit mimarisine
    // göre farklı zamanlanabildiği için CI'da yanlış bir platform hatası veriyordu.
    fireEvent.input(speed, { target: { value: "1.35" } });
    fireEvent.mouseUp(speed);

    await waitFor(() =>
      expect(client.request).toHaveBeenCalledWith(
        "ses.ayar",
        expect.objectContaining({ hiz: 1.35 }),
      ),
    );
    await waitFor(() => expect(screen.getByText("1.35×")).toBeTruthy());
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("model uygulamayla geldiği için indirme ve model seçme düğmesi yoktur", async () => {
    render(<VoicePreferences client={voiceClient({ installed: true })} />);
    await screen.findByText("EMA Lightning · EMA Lightning");
    expect(screen.queryByRole("button", { name: /indir/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /model seç/i })).toBeNull();
  });
});
