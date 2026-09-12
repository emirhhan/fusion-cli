import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";
import { CodeCard } from "./CodeCard";
import { canonicalLanguage } from "./highlight";

afterEach(cleanup);

const UZUN_KOD = ["bir", "iki", "üç", "dört", "beş", "altı", "yedi"].join("\n");

describe("canonicalLanguage", () => {
  test("takma adları kanonik dile indirir", () => {
    expect(canonicalLanguage("js")).toBe("javascript");
    expect(canonicalLanguage("PY")).toBe("python");
    expect(canonicalLanguage("c++")).toBe("cpp");
    expect(canonicalLanguage("gd")).toBe("gdscript");
  });

  test("tanınmayan etiket için null döner", () => {
    expect(canonicalLanguage("brainfuck")).toBeNull();
    expect(canonicalLanguage("")).toBeNull();
  });
});

describe("CodeCard", () => {
  test("kısa kodda katlama düğmesi çizilmez", () => {
    render(<CodeCard code={"tek satır"} />);

    expect(screen.queryByRole("button", { name: /Kodu göster/ })).toBeNull();
  });

  test("uzun kod kapalı başlar ve yalnız ilk beş satırı gösterir", () => {
    const { container } = render(<CodeCard code={UZUN_KOD} />);

    const govde = container.querySelector(".code-card__body")?.textContent ?? "";
    expect(govde).toContain("beş");
    expect(govde).not.toContain("altı");
    expect(container.querySelector(".code-card")?.getAttribute("data-open")).toBe("false");
  });

  test("düğmeye basınca tüm satırlar görünür", () => {
    const { container } = render(<CodeCard code={UZUN_KOD} />);

    fireEvent.click(screen.getByRole("button", { name: /Kodu göster · 7 satır/ }));

    expect(container.querySelector(".code-card__body")?.textContent).toContain("yedi");
    expect(container.querySelector(".code-card")?.getAttribute("data-open")).toBe("true");
    expect(screen.getByRole("button", { name: "Gizle" })).toBeTruthy();
  });

  test("kopyala düğmesi kodun tamamını panoya yazar", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });

    render(<CodeCard code={UZUN_KOD} />);
    fireEvent.click(screen.getByRole("button", { name: "Kodu kopyala" }));

    expect(writeText).toHaveBeenCalledWith(UZUN_KOD);
    expect(await screen.findByText("Kopyalandı")).toBeTruthy();
  });

  test("dosya adına tıklamak dosyayı açma isteğini iletir", () => {
    const onOpenFile = vi.fn();
    render(<CodeCard code="extends Node" filename="scripts/Player.gd" language="gdscript" onOpenFile={onOpenFile} />);

    fireEvent.click(screen.getByRole("button", { name: /Player.gd/ }));

    expect(onOpenFile).toHaveBeenCalledWith("scripts/Player.gd");
  });

  test("açma geri çağrısı yoksa dosya adı düz metin kalır", () => {
    const { container } = render(<CodeCard code="x" filename="a.py" language="python" />);

    expect(container.querySelector(".code-card__name--link")).toBeNull();
    expect(container.querySelector(".code-card__name")?.textContent).toBe("a.py");
  });
});
