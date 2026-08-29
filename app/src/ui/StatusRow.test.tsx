import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { StatusRow } from "./StatusRow";

afterEach(cleanup);

describe("StatusRow", () => {
  it("başlık, açıklama ve durumu yoğun bir satırda gösterir", () => {
    render(<StatusRow description="Yerel çalışma zamanı" label="Fusion" status="Hazır" tone="success" />);
    expect(screen.getByText("Fusion")).toBeTruthy();
    expect(screen.getByText("Yerel çalışma zamanı")).toBeTruthy();
    expect(screen.getByText("Hazır")).toBeTruthy();
  });

  it("durumu yalnız renkle değil metin ve veri niteliğiyle taşır", () => {
    const { container } = render(<StatusRow label="Gateway" status="Kapalı" tone="neutral" />);
    expect(container.querySelector('[data-tone="neutral"]')?.textContent).toContain("Kapalı");
  });
});
