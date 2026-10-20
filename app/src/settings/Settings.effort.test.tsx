import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import type { ProtocolClient } from "../protocol/client";
import { Settings } from "./Settings";

afterEach(cleanup);

test("yoğunluk komutu pending boyunca tek çalışır ve başarı sonrası gerçek snapshot yenilenir", async () => {
  let effort = "auto";
  let finish!: (value: { ok: true }) => void;
  const command = vi.fn((_command: string) => new Promise<{ ok: true }>((resolve) => { finish = resolve; }));
  const request = vi.fn(async () => ({ ok: true, model: { agent: "model-A", hakem: "", adaylar: [], saglayici: "", yogunluk: effort, yogunluk_dogrulandi: true, desteklenen_yogunluklar: ["high"] } }));
  render(<Settings initialSection="modeller" client={{ request } as unknown as ProtocolClient} onClose={vi.fn()} onThemeChange={vi.fn()} themePreference="system" onRunCommand={command} />);
  const select = await screen.findByRole("combobox", { name: "Düşünme yoğunluğu" }) as HTMLSelectElement;
  fireEvent.change(select, { target: { value: "high" } });
  expect(select.disabled).toBe(true);
  fireEvent.change(select, { target: { value: "high" } });
  expect(command).toHaveBeenCalledExactlyOnceWith("/effort high");
  effort = "high";
  await act(async () => finish({ ok: true }));
  await waitFor(() => expect(select.value).toBe("high"));
  expect(select.disabled).toBe(false);
});

test("reddedilen yoğunluk eski seçimi korur ve yalnız ilgili komut yeniden denenir", async () => {
  const command = vi.fn(async (_command: string) => ({ ok: false as const, message: "Yoğunluk reddedildi." }));
  const request = vi.fn(async () => ({ ok: true, model: { agent: "model-A", hakem: "", adaylar: [], saglayici: "", yogunluk: "auto", yogunluk_dogrulandi: true, desteklenen_yogunluklar: ["high"] } }));
  render(<Settings initialSection="modeller" client={{ request } as unknown as ProtocolClient} onClose={vi.fn()} onThemeChange={vi.fn()} themePreference="system" onRunCommand={command} />);
  const select = await screen.findByRole("combobox", { name: "Düşünme yoğunluğu" }) as HTMLSelectElement;
  fireEvent.change(select, { target: { value: "high" } });
  expect(await screen.findByRole("alert")).toHaveProperty("textContent", expect.stringContaining("Yoğunluk reddedildi."));
  expect(select.value).toBe("auto");
  fireEvent.click(screen.getByRole("button", { name: "Yeniden dene" }));
  await waitFor(() => expect(command).toHaveBeenCalledTimes(2));
  expect(command.mock.calls.every(([value]) => value === "/effort high")).toBe(true);
});
