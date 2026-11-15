import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ProtocolClient } from "../protocol/client";
import { useBrowserInspector } from "./useBrowserInspector";

afterEach(cleanup);

type Listener = (event: Record<string, unknown>) => void;

function istemci(ajanGoruyor: boolean) {
  const listeners: Listener[] = [];
  const request = vi.fn(async () => ({ ok: true, ajan_goruyor: ajanGoruyor }));
  const client = {
    request,
    onEvent: (listener: Listener) => { listeners.push(listener); return () => undefined; },
  } as unknown as ProtocolClient;
  const emit = (event: Record<string, unknown>) => act(() => { listeners.forEach((listener) => listener(event)); });
  return { client, request, emit };
}

const acildi = { olay: "ToolExecuted", name: "browser_open", outcome: "ok" };

describe("useBrowserInspector (Tarayıcı sekmesine geçiş, P-045)", () => {
  it("ajan paneli paylaşıyorsa browser_open sonrası Tarayıcı sekmesine geçer", async () => {
    const { client, request, emit } = istemci(true);
    const show = vi.fn();
    renderHook(() => useBrowserInspector(client, show));

    emit(acildi);

    await waitFor(() => expect(show).toHaveBeenCalledTimes(1));
    expect(request).toHaveBeenCalledWith("tarayici_panel.durum", {});
  });

  it("ajan kendi tarayıcısını kullanıyorsa (paylaşım kapalı) sekme değişmez", async () => {
    // Ölçüldü (31 Ekim, inceleme): sekme her browser_open'da öne geliyor, panel ajanın
    // tarayıcısını göstermediği için boş "Uygulama içi tarayıcı" kalıyordu.
    const { client, request, emit } = istemci(false);
    const show = vi.fn();
    renderHook(() => useBrowserInspector(client, show));

    emit(acildi);

    await waitFor(() => expect(request).toHaveBeenCalled());
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(show).not.toHaveBeenCalled();
  });
});
