import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import type { ProtocolClient } from "../protocol/client";
import { DevToolsCheck, parseDevTools } from "./DevToolsCheck";

afterEach(cleanup);

const rows = [
  { id: "node", ad: "Node.js", neden: "Web projeleri için.", kurulu: true, surum: "v22.1.0", indirme: "https://nodejs.org/en/download" },
  { id: "python", ad: "Python", neden: "Python projeleri için.", kurulu: false, surum: null, indirme: "https://www.python.org/downloads/" },
];

it("kurulu aracı sürümüyle, eksik aracı indirme bağlantısıyla gösterir; kendisi kurmaz", async () => {
  const request = vi.fn(async () => ({ ok: true, araclar: rows }));
  render(<DevToolsCheck client={{ request } as unknown as ProtocolClient} />);

  expect(await screen.findByText("v22.1.0")).toBeTruthy();
  const link = screen.getByRole("link", { name: "İndirme sayfasını aç" });
  expect(link.getAttribute("href")).toBe("https://www.python.org/downloads/");
  expect(link.getAttribute("rel")).toContain("noopener");
  expect(screen.getByText("Eksik")).toBeTruthy();
  expect(request).toHaveBeenCalledTimes(1);
  expect(request).toHaveBeenCalledWith("araclar.algila", {});
});

it("algılama başarısız olursa hata gösterir", async () => {
  const request = vi.fn(async () => ({ ok: false, metin: "Araçlar okunamadı." }));
  render(<DevToolsCheck client={{ request } as unknown as ProtocolClient} />);
  expect((await screen.findByRole("alert")).textContent).toContain("Araçlar okunamadı.");
});

it("geçersiz satırları atlar", () => {
  expect(parseDevTools({ araclar: [{ id: 3 }, rows[0]] })).toHaveLength(1);
  expect(parseDevTools({})).toEqual([]);
});
