import { renderHook } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import type { ProtocolClient } from "../protocol/client";
import type { ProjectRegistry } from "../sessions/projectRecords";
import { markRemoteInUse } from "./remoteFlag";
import { useRemoteProjectSync } from "./useRemoteProjectSync";

const registry: ProjectRegistry = {
  projects: [{ id: "p1", name: "Site", root: "/k/site", createdAt: 1 }],
  chats: { c1: "p1" },
};
const client = () => ({ request: vi.fn(async () => ({ ok: true })) }) as unknown as ProtocolClient & { request: ReturnType<typeof vi.fn> };

beforeEach(() => window.localStorage.clear());

it("uzaktan erişim kullanılmıyorsa proje kaydı gönderilmez", () => {
  const c = client();
  renderHook(() => useRemoteProjectSync(c, registry));
  expect(c.request).not.toHaveBeenCalled();
});

it("kullanılıyorsa projeleri ve sohbet eşlemesini çekirdeğe eşitler", () => {
  markRemoteInUse(true);
  const c = client();
  renderHook(() => useRemoteProjectSync(c, registry));
  expect(c.request).toHaveBeenCalledWith("uzak.projeler_esitle", { projeler: registry.projects, sohbetler: registry.chats });
});
