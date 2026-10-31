import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ProtocolClient } from "../protocol/client";
import type { SessionModel } from "../sessions/types";
import { SplitPane } from "./SplitPane";

afterEach(cleanup);

function oturum(degisiklik: Partial<SessionModel> = {}): SessionModel {
  return {
    id: "b", title: "Tema işi", source: "fusion", root: "/proje", pid: 1, status: "ready", error: null,
    running: false, messages: [{ rol: "asistan", metin: "Hazırım." }], question: null,
    baglam: null, maliyetUsd: null, depoProjeleri: [], client: {} as ProtocolClient,
    ...degisiklik,
  };
}

describe("SplitPane (P-064)", () => {
  it("ikinci sohbetin akışını, durumunu ve mesaj kutusunu çizer; Enter gönderir", () => {
    const onSend = vi.fn();
    render(<SplitPane onAnswer={vi.fn()} onClose={vi.fn()} onFocus={vi.fn()} onSend={onSend} session={oturum()} showSteps={false} />);
    expect(screen.getByText("Hazırım.")).toBeTruthy();
    expect(screen.getByText("Hazır")).toBeTruthy();
    const kutu = screen.getByLabelText("Tema işi sohbetine mesaj");
    fireEvent.change(kutu, { target: { value: "devam et" } });
    fireEvent.keyDown(kutu, { key: "Enter" });
    expect(onSend).toHaveBeenCalledWith("devam et");
    expect((kutu as HTMLTextAreaElement).value).toBe("");
  });

  it("boş mesaj gönderilmez; 'Bu sohbete geç' ve kapatma çağrılır", () => {
    const onSend = vi.fn();
    const onFocus = vi.fn();
    const onClose = vi.fn();
    render(<SplitPane onAnswer={vi.fn()} onClose={onClose} onFocus={onFocus} onSend={onSend} session={oturum()} showSteps={false} />);
    fireEvent.keyDown(screen.getByLabelText("Tema işi sohbetine mesaj"), { key: "Enter" });
    expect(onSend).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Bu sohbete geç" }));
    fireEvent.click(screen.getByRole("button", { name: "Yan bölmeyi kapat" }));
    expect(onFocus).toHaveBeenCalledOnce();
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("bekleyen soru bölmede onay kartı olarak görünür ve cevap iletilir", () => {
    const onAnswer = vi.fn();
    const session = oturum({ running: true, question: { id: "s1", data: { tur: "soru", soru: "Hangi renk?", secenekler: [{ etiket: "Mavi", deger: "mavi" }] } } });
    render(<SplitPane onAnswer={onAnswer} onClose={vi.fn()} onFocus={vi.fn()} onSend={vi.fn()} session={session} showSteps={false} />);
    expect(screen.getByText("Hangi renk?")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /Mavi/ }));
    expect(onAnswer).toHaveBeenCalled();
  });
});
