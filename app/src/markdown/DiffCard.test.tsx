import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";
import { DiffCard, countChanges, parseDiff } from "./DiffCard";

afterEach(cleanup);

const DIFF = [
  "--- a/scripts/Player.gd",
  "+++ b/scripts/Player.gd",
  "@@ -1,4 +1,5 @@",
  " extends CharacterBody2D",
  "-var speed = 100",
  "+var speed = 320",
  "+var dash_speed = 900",
  " func _ready():",
].join("\n");

describe("parseDiff", () => {
  test("satırları türüne göre ayırır", () => {
    const rows = parseDiff(DIFF);

    expect(rows[0].kind).toBe("meta");
    expect(rows[1].kind).toBe("meta");
    expect(rows[2].kind).toBe("hunk");
    expect(rows[3].kind).toBe("context");
    expect(rows[4].kind).toBe("remove");
    expect(rows[5].kind).toBe("add");
  });

  test("ekleme ve silme sayısını verir; başlık satırlarını saymaz", () => {
    expect(countChanges(parseDiff(DIFF))).toEqual({ added: 2, removed: 1 });
  });
});

describe("DiffCard", () => {
  test("dosya yolunu ve değişiklik özetini başlıkta gösterir", () => {
    render(<DiffCard diff={DIFF} path="scripts/Player.gd" />);

    expect(screen.getByText("scripts/Player.gd")).toBeTruthy();
    expect(screen.getByText("+2")).toBeTruthy();
    expect(screen.getByText("−1")).toBeTruthy();
  });

  test("uzun diff kapalı başlar, düğmeyle tamamı açılır", () => {
    const { container } = render(<DiffCard diff={DIFF} path="a.gd" />);

    expect(container.querySelector(".code-card__body")?.textContent).not.toContain("func _ready");

    fireEvent.click(screen.getByRole("button", { name: /Değişikliği göster/ }));

    expect(container.querySelector(".code-card__body")?.textContent).toContain("func _ready");
  });

  /* Renk TEK işaret olamaz: renk körü kullanıcı da eklemeyi silmeden
     ayırabilmeli, bu yüzden +/- karakterleri satırda kalır. */
  test("satır türünü hem veri niteliğiyle hem +/- karakteriyle işaretler", () => {
    const { container } = render(<DiffCard diff={DIFF} path="a.gd" />);
    fireEvent.click(screen.getByRole("button", { name: /Değişikliği göster/ }));

    const eklenen = container.querySelector('[data-kind="add"]');
    const silinen = container.querySelector('[data-kind="remove"]');
    expect(eklenen?.textContent?.startsWith("+")).toBe(true);
    expect(silinen?.textContent?.startsWith("-")).toBe(true);
  });

  test("dosya yoluna tıklamak dosyayı açma isteğini iletir", () => {
    const onOpenFile = vi.fn();
    render(<DiffCard diff={DIFF} onOpenFile={onOpenFile} path="scripts/Player.gd" />);

    fireEvent.click(screen.getByRole("button", { name: /Player.gd/ }));

    expect(onOpenFile).toHaveBeenCalledWith("scripts/Player.gd");
  });
});
