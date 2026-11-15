import { describe, expect, it, vi } from "vitest";
import { renameConversation } from "./renameConversation";

describe("renameConversation (#443)", () => {
  it("sohbet.adlandir isteğini kimlik ve kırpılmış adla gönderir", async () => {
    const request = vi.fn().mockResolvedValue({ ok: true, sohbet_id: "s1", ad: "Yeni ad" });
    await expect(renameConversation({ request }, "s1", "  Yeni ad ")).resolves.toBe("Yeni ad");
    expect(request).toHaveBeenCalledWith("sohbet.adlandir", { sohbet_id: "s1", ad: "Yeni ad" });
  });

  it("boş adı göndermez, çekirdek hatasını iletir", async () => {
    const request = vi.fn().mockResolvedValue({ ok: false, metin: "Kullanım: /rename <ad>" });
    await expect(renameConversation({ request }, "s1", "  ")).rejects.toThrow("boş");
    expect(request).not.toHaveBeenCalled();
    await expect(renameConversation({ request }, "s1", "Ad")).rejects.toThrow("Kullanım");
  });
});
