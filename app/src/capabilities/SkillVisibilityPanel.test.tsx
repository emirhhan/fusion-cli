import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ProtocolClient } from "../protocol/client";
import { SkillVisibilityPanel } from "./SkillVisibilityPanel";
import { SkillsCatalog } from "./SkillsCatalog";

afterEach(cleanup);

function client() {
  return {
    request: vi.fn(async (name: string, data: Record<string, unknown>) => {
      if (name === "yetenek.gorunurluk_listesi") return {
        ok: true,
        beceriler: [
          { ad: "alfa", kaynak: "claude", aciklama: "kısa", gorunurluk: "on", belirtec: 5 },
          { ad: "beta", kaynak: "claude", aciklama: "uzun açıklama", gorunurluk: "off", belirtec: 40 },
        ],
      };
      if (name === "yetenek.gorunurluk") return { ok: true, gorunurluk: "name-only", metin: `skillOverrides kaydedildi: ${String(data.ad)}: name-only` };
      if (name === "yetenek.katalog") return { ok: true, beceriler: [] };
      return { ok: true };
    }),
  } as unknown as ProtocolClient;
}

const names = () => screen.getAllByRole("listitem").map((item) => item.querySelector("strong")?.textContent);

describe("SkillVisibilityPanel (#176)", () => {
  it("kapalılar dahil listeler, süzer ve token sırasına geçer", async () => {
    render(<SkillVisibilityPanel client={client()} />);
    await screen.findByText("alfa");
    expect(names()).toEqual(["alfa", "beta"]);
    expect(screen.getByRole("button", { name: "beta görünürlüğü: off" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Token sırası" }));
    expect(names()).toEqual(["beta", "alfa"]);
    fireEvent.change(screen.getByLabelText("Becerileri süz"), { target: { value: "kıs" } });
    expect(names()).toEqual(["alfa"]);
  });

  it("görünürlük düğmesi döndürür, kaydeder ve satırı günceller", async () => {
    const c = client();
    const changed = vi.fn();
    render(<SkillVisibilityPanel client={c} onChanged={changed} />);
    fireEvent.click(await screen.findByRole("button", { name: "alfa görünürlüğü: on" }));
    expect(await screen.findByText("skillOverrides kaydedildi: alfa: name-only")).toBeTruthy();
    expect(c.request).toHaveBeenCalledWith("yetenek.gorunurluk", { ad: "alfa" });
    expect(screen.getByRole("button", { name: "alfa görünürlüğü: name-only" })).toBeTruthy();
    await waitFor(() => expect(changed).toHaveBeenCalled());
  });

  it("katalogdaki Görünürlük düğmesi paneli açar", async () => {
    render(<SkillsCatalog client={client()} onClose={() => undefined} />);
    fireEvent.click(await screen.findByRole("button", { name: "Görünürlük" }));
    expect(await screen.findByRole("region", { name: "Beceri görünürlüğü" })).toBeTruthy();
  });
});
