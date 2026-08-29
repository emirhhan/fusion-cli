import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { Conversation } from "./Conversation";

afterEach(cleanup);

describe("Conversation", () => {
  it("kullanıcıyı balonda, Fusion yanıtını balonsuz makalede gösterir", () => {
    const { container } = render(
      <Conversation
        mesajlar={[
          { rol: "kullanici", metin: "Bir oyun yap" },
          { rol: "asistan", metin: "Oyunu hazırladım." },
        ]}
      />,
    );
    expect(container.querySelector(".conversation__message--user")).toBeTruthy();
    expect(screen.getByRole("article", { name: "Fusion yanıtı" })).toBeTruthy();
    expect(container.querySelector(".conversation__message--assistant")?.className).not.toContain(
      "conversation__bubble",
    );
  });

  it("çalışma olayını açılabilir ayrıntı olarak sunar", () => {
    render(<Conversation mesajlar={[{ rol: "olay", metin: "Dosya yazıldı: index.html" }]} />);
    expect(screen.getByText("Dosya yazıldı: index.html").closest("details")).toBeTruthy();
  });

  it("uzun ve satır sonlu metni güvenli metin akışında korur", () => {
    const { container } = render(
      <Conversation mesajlar={[{ rol: "asistan", metin: "ilk satır\nikinci satır" }]} />,
    );
    expect(container.querySelector(".conversation__text")?.textContent).toContain("ikinci satır");
  });
});
