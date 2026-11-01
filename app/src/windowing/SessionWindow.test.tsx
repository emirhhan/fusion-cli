import { act, cleanup, fireEvent, render, renderHook, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import type { SessionModel } from "../sessions/types";
import { SessionWindow } from "./SessionWindow";
import {
  parseAction,
  SESSION_WINDOW_ACTION,
  SESSION_WINDOW_STATE,
  sessionWindowId,
  type WindowEvents,
} from "./sessionWindowBridge";
import { useSessionWindows } from "./useSessionWindows";

afterEach(cleanup);

/** Pencereler arası olay veriyolunun bellekteki eşi. */
function bus() {
  const handlers = new Map<string, Set<(payload: unknown) => void>>();
  const sent: { event: string; payload: unknown }[] = [];
  const events: WindowEvents = {
    emit: async (event, payload) => {
      sent.push({ event, payload });
      for (const handler of handlers.get(event) ?? []) handler(payload);
    },
    listen: async (event, handler) => {
      const set = handlers.get(event) ?? new Set();
      set.add(handler);
      handlers.set(event, set);
      return () => set.delete(handler);
    },
  };
  return { events, sent };
}

const session = {
  id: "s1", title: "Site işi", running: false, status: "ready", question: null,
  messages: [{ rol: "kullanici", metin: "Merhaba" }, { rol: "asistan", metin: "Selam" }],
} as unknown as SessionModel;

it("pencere adresi yalnız geçerli sohbet kimliğini kabul eder (#443)", () => {
  expect(sessionWindowId("?pencere=oturum&oturum=abc-1")).toBe("abc-1");
  expect(sessionWindowId("?pencere=oturum&oturum=../x")).toBeNull();
  expect(sessionWindowId("?pencere=ses")).toBeNull();
  expect(parseAction({ id: "s1", tur: "gonder", gorev: " " })).toBeNull();
  expect(parseAction({ id: "s1", tur: "bilinmez" })).toBeNull();
});

it("ana pencere durumu yayar; pencereden gönderilen mesaj ve onay ana pencereye gider", async () => {
  const { events, sent } = bus();
  const handlers = { send: vi.fn(), answer: vi.fn(), focus: vi.fn() };
  renderHook(() => useSessionWindows([session], handlers, { enabled: true, events }));
  await act(async () => { await Promise.resolve(); });
  render(<SessionWindow closeWindow={vi.fn()} events={events} id="s1" />);
  expect(await screen.findByText("Selam")).toBeTruthy();
  expect(sent.some((item) => item.event === SESSION_WINDOW_ACTION && (item.payload as { tur: string }).tur === "hazir")).toBe(true);
  expect(sent.some((item) => item.event === SESSION_WINDOW_STATE)).toBe(true);
  const box = screen.getByLabelText("Site işi sohbetine mesaj");
  fireEvent.change(box, { target: { value: "Devam et" } });
  fireEvent.keyDown(box, { key: "Enter" });
  await act(async () => { await Promise.resolve(); });
  expect(handlers.send).toHaveBeenCalledWith("s1", "Devam et");
  fireEvent.click(screen.getByRole("button", { name: "Bu sohbete geç" }));
  await act(async () => { await Promise.resolve(); });
  expect(handlers.focus).toHaveBeenCalledWith("s1");
});

it("başka sohbetin durumu bu pencereye çizilmez", async () => {
  const { events } = bus();
  render(<SessionWindow closeWindow={vi.fn()} events={events} id="s2" />);
  await act(async () => { await events.emit(SESSION_WINDOW_STATE, { ...session, id: "s1" }); });
  expect(screen.getByRole("status").textContent).toContain("yükleniyor");
});
