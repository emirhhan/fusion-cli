import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AttachmentChip } from "./AttachmentChip";

vi.mock("../platform/assetUrl", () => ({
  assetUrl: (path: string) => (path.startsWith("/yok") ? null : `asset://${path}`),
}));

afterEach(cleanup);

describe("AttachmentChip", () => {
  it("görsel ekte önizleme gösterir", () => {
    render(
      <AttachmentChip
        attachment={{ kind: "image", name: "ekran.png", path: "/tmp/ekran.png" }}
        onRemove={() => undefined}
      />,
    );
    const gorsel = screen.getByRole("img", { name: "ekran.png önizlemesi" }) as HTMLImageElement;
    expect(gorsel.getAttribute("src")).toBe("asset:///tmp/ekran.png");
  });

  it("görsel olmayan ekte önizleme çizmez", () => {
    render(
      <AttachmentChip
        attachment={{ kind: "file", name: "not.txt", path: "/tmp/not.txt" }}
        onRemove={() => undefined}
      />,
    );
    expect(screen.queryByRole("img")).toBeNull();
    expect(screen.getByText("not.txt")).toBeTruthy();
  });

  it("önizleme yüklenemezse simgeye düşer, kırık kutu bırakmaz", () => {
    render(
      <AttachmentChip
        attachment={{ kind: "image", name: "ekran.png", path: "/tmp/ekran.png" }}
        onRemove={() => undefined}
      />,
    );
    fireEvent.error(screen.getByRole("img", { name: "ekran.png önizlemesi" }));
    expect(screen.queryByRole("img")).toBeNull();
  });

  it("kaldırma düğmesi çalışır", () => {
    const onRemove = vi.fn();
    render(
      <AttachmentChip
        attachment={{ kind: "image", name: "ekran.png", path: "/tmp/ekran.png" }}
        onRemove={onRemove}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "ekran.png ekini kaldır" }));
    expect(onRemove).toHaveBeenCalled();
  });
});
