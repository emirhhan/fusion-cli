import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Conversation } from "../screens/Conversation";

afterEach(cleanup);

describe("Konuşmada hata bildirimi", () => {
  it("yalnız başarısız yanıtta 'Hatayı bildir' çıkar ve metni iletir", () => {
    const onHataBildir = vi.fn();
    render(
      <Conversation
        mesajlar={[
          { rol: "asistan", metin: "Her şey yolunda" },
          { rol: "asistan", metin: "Model zaman aşımına uğradı", hata: true },
          // Yalnız metin ön eki hata sayılmaz: model "Hata: ..." diye meşru açıklama yazabilir (U1-28).
          { rol: "asistan", metin: "Hata: bağlantı koptu (örnek açıklama)" },
        ]}
        onHataBildir={onHataBildir}
        running={false}
      />,
    );
    const dugmeler = screen.getAllByRole("button", { name: "Hatayı bildir" });
    expect(dugmeler).toHaveLength(1);
    fireEvent.click(dugmeler[0]);
    expect(onHataBildir).toHaveBeenCalledWith("Model zaman aşımına uğradı");
  });

  it("geri çağırım verilmezse düğme çizilmez", () => {
    render(<Conversation mesajlar={[{ rol: "asistan", metin: "Hata: x", hata: true }]} running={false} />);
    expect(screen.queryByRole("button", { name: "Hatayı bildir" })).toBeNull();
  });
});
