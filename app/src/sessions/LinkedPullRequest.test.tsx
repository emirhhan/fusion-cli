import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ProtocolClient } from "../protocol/client";
import { LinkedPullRequest, prFrom } from "./LinkedPullRequest";

afterEach(cleanup);

function client(pr: unknown) {
  return { request: vi.fn(async () => ({ ok: true, pr })) } as unknown as ProtocolClient;
}

describe("LinkedPullRequest (P-057)", () => {
  it("bağlı PR'ı rozet olarak gösterir ve tıklanınca adresi açar", async () => {
    const open = vi.fn(async () => undefined);
    render(<LinkedPullRequest client={client({ numara: 12, url: "https://github.com/a/b/pull/12", depo: "a/b" })} open={open} />);
    const button = await screen.findByRole("button", { name: "Bağlı PR #12 (a/b) — tarayıcıda aç" });
    fireEvent.click(button);
    expect(open).toHaveBeenCalledWith("https://github.com/a/b/pull/12");
  });

  it("PR yoksa ya da adres https değilse hiçbir şey çizmez", async () => {
    const fake = client(null);
    const { container } = render(<LinkedPullRequest client={fake} />);
    await waitFor(() => expect(fake.request).toHaveBeenCalled());
    expect(container.textContent).toBe("");
    expect(prFrom({ numara: 3, url: "javascript:alert(1)" })).toBeNull();
  });

  it("tur sürerken okumaz, tur bitince yeniden okur", async () => {
    const fake = client({ numara: 7, url: "https://github.com/a/b/pull/7" });
    const { rerender } = render(<LinkedPullRequest client={fake} running />);
    expect(fake.request).not.toHaveBeenCalled();
    rerender(<LinkedPullRequest client={fake} running={false} />);
    expect(await screen.findByText("PR #7")).toBeTruthy();
  });
});
