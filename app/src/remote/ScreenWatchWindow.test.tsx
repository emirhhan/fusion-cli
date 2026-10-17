import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type { ProtocolClient } from "../protocol/client";
import { markRemoteInUse } from "./remoteFlag";
import { ScreenWatchWindow, WATCH_POLL_MS } from "./ScreenWatchWindow";

beforeEach(() => { vi.useFakeTimers(); window.localStorage.clear(); });
afterEach(() => { cleanup(); vi.useRealTimers(); });

function fakeClient(live: { cihazId: string; ad: string }[]) {
  return {
    request: vi.fn(async (name: string) => {
      if (name === "uzak.ekran_bekleyen") return { ok: true, bekleyen: [], etkin: live };
      if (name === "uzak.ekran_onizleme") return { ok: true, seq: 1, jpegBase64: "AAAA" };
      return { ok: true };
    }),
  } as unknown as ProtocolClient;
}

async function tick(ms = 10) { await act(async () => { await vi.advanceTimersByTimeAsync(ms); }); }

it("uzaktan erişim kullanılmıyorsa çekirdeğe hiç istek göndermez", async () => {
  const client = fakeClient([{ cihazId: "d1", ad: "Telefonum" }]);
  render(<ScreenWatchWindow client={client} />);
  await tick(WATCH_POLL_MS * 2);
  expect((client.request as ReturnType<typeof vi.fn>).mock.calls.length).toBe(0);
  expect(screen.queryByRole("region", { name: "Ekran izleme" })).toBeNull();
});

it("telefon izlerken telefonun gördüğü kareyi küçük pencerede gösterir", async () => {
  markRemoteInUse(true);
  const client = fakeClient([{ cihazId: "d1", ad: "Telefonum" }]);
  render(<ScreenWatchWindow client={client} />);
  await tick();
  await tick();
  expect(screen.getByText("Telefonum ekranını izliyor")).toBeTruthy();
  const image = (screen.getByAltText("Telefonum cihazının gördüğü ekran")) as HTMLImageElement;
  expect(image.src).toBe("data:image/jpeg;base64,AAAA");
  expect(client.request).toHaveBeenCalledWith("uzak.ekran_onizleme", { cihazId: "d1" });
});

it("Kapat yalnız pencereyi gizler; Kes paylaşımı çekirdekte keser", async () => {
  markRemoteInUse(true);
  const client = fakeClient([{ cihazId: "d1", ad: "Telefonum" }]);
  render(<ScreenWatchWindow client={client} />);
  await tick();
  await tick();
  fireEvent.click(screen.getByRole("button", { name: "Kes" }));
  expect(client.request).toHaveBeenCalledWith("uzak.ekran_kes", { cihazId: "d1" });
  fireEvent.click(screen.getByRole("button", { name: "İzleme penceresini kapat" }));
  expect(screen.queryByRole("region", { name: "Ekran izleme" })).toBeNull();
  expect((client.request as ReturnType<typeof vi.fn>).mock.calls.filter(([name]) => name === "uzak.ekran_kes").length).toBe(1);
});
