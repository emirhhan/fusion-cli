import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ProtocolClient } from "../protocol/client";
import { VoicePreferences } from "./VoicePreferences";

afterEach(cleanup);

function voiceClient(options: { installed?: boolean } = {}) {
  const state = {
    hiz: 1,
    model: null as string | null,
    robotik: 0.5,
  };
  return {
    onEvent: vi.fn(() => () => undefined),
    request: vi.fn(async (name: string, data: Record<string, unknown>) => {
      if (name === "ses.durum") {
        return {
          ok: true,
          ayar: { ...state },
          kullanilabilir: true,
          model_kurulu: options.installed ?? false,
          motor: options.installed ? "piper" : "sistem",
          ses: options.installed ? "tr_TR-dfki-medium" : "Cem",
          turkce: true,
          yukseltme: null,
        };
      }
      if (name === "ses.ayar") {
        Object.assign(state, data);
        return { ok: true, ...state };
      }
      if (name === "ses.model_indir") {
        options.installed = true;
        return { ok: true, yol: "/voices/tr_TR-dfki-medium.onnx" };
      }
      return { ok: false, metin: "Bilinmeyen istek" };
    }),
  } as unknown as ProtocolClient;
}

describe("VoicePreferences", () => {
  it("gerçek motoru ve kayıtlı ses tercihlerini gösterir", async () => {
    render(<VoicePreferences client={voiceClient({ installed: true })} />);

    expect(await screen.findByText("Piper · tr_TR-dfki-medium")).toBeTruthy();
    expect(screen.getByText("1.00×")).toBeTruthy();
    expect(screen.getByText("50%")).toBeTruthy();
  });

  it("değiştirilen hızı çekirdeğe kaydedip ekranda korur", async () => {
    const client = voiceClient();
    render(<VoicePreferences client={client} />);
    const speed = await screen.findByLabelText("Hız");

    fireEvent.change(speed, { target: { value: "1.35" } });
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

  it("Fusion Türkçe modelini uygulama içinden indirir", async () => {
    render(<VoicePreferences client={voiceClient()} />);

    fireEvent.click(await screen.findByRole("button", { name: "Türkçe modeli indir" }));

    expect(await screen.findByText("Piper · tr_TR-dfki-medium")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Türkçe modeli indir" })).toBeNull();
  });

  it("geçerli Piper modelini seçip dosya adını gösterir", async () => {
    render(
      <VoicePreferences
        client={voiceClient()}
        selectModel={async () => "/Users/test/sesler/ozel.onnx"}
      />,
    );

    fireEvent.click(await screen.findByRole("button", { name: "Piper ses modeli seç" }));

    expect(await screen.findByText("ozel.onnx")).toBeTruthy();
  });
});
