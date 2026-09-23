import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";
import { ModelPicker, shortModelName, type ModelOption } from "./ModelPicker";

afterEach(cleanup);

const SECENEKLER: ModelOption[] = [
  { deger: "/model agent gemini_web/main", etiket: "Gemini Web", aciklama: "Tarayıcı oturumu" },
  { deger: "/model agent openrouter/openai/gpt-oss-20b:free", etiket: "GPT-OSS 20B", aciklama: "Ücretsiz" },
];

describe("shortModelName", () => {
  test("sağlayıcı önekini atıp son parçayı bırakır", () => {
    expect(shortModelName("openrouter/openai/gpt-oss-20b:free")).toBe("gpt-oss-20b:free");
    expect(shortModelName("gemini_web")).toBe("gemini_web");
  });

  test("model yoksa yönlendirici bir etiket verir", () => {
    expect(shortModelName("")).toBe("Model seç");
  });
});

describe("ModelPicker", () => {
  test("etkin modeli düğmede gösterir, tam adı başlıkta saklar", () => {
    render(<ModelPicker active="openrouter/openai/gpt-oss-20b:free" onSelect={vi.fn()} options={[]} />);

    const dugme = screen.getByRole("button");
    expect(dugme.textContent).toContain("gpt-oss-20b:free");
    expect(dugme.getAttribute("title")).toBe("openrouter/openai/gpt-oss-20b:free");
  });

  test("seçilen web modelinin gerçek etiketini otomatik kimliği yerine gösterir", () => {
    render(<ModelPicker active="gemini_web/main/auto" activeLabel="Gemini · 3.1 Pro" onSelect={vi.fn()} options={[]} />);
    const button = screen.getByRole("button", { name: /Gemini · 3.1 Pro/ });
    expect(button.textContent).toContain("Gemini · 3.1 Pro");
  });

  test("liste kapalıyken seçenek çizilmez", () => {
    render(<ModelPicker active="a" onSelect={vi.fn()} options={SECENEKLER} />);

    expect(screen.queryByRole("listbox")).toBeNull();
  });

  /* Seçenekler TEMBEL yüklenir: her sohbet açılışında model listesi çekmek
     gereksiz bir istek, web sağlayıcıda ise gereksiz bir tarayıcı turudur. */
  test("liste ilk açılışta yüklemeyi tetikler", () => {
    const onOpen = vi.fn();
    render(<ModelPicker active="a" onOpen={onOpen} onSelect={vi.fn()} options={SECENEKLER} />);

    fireEvent.click(screen.getByRole("button", { name: /Model:/ }));

    expect(onOpen).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("listbox")).toBeTruthy();
    expect(screen.getByText("Gemini Web")).toBeTruthy();
  });

  test("seçim komutu olduğu gibi iletilir ve liste kapanır", () => {
    const onSelect = vi.fn();
    render(<ModelPicker active="a" onSelect={onSelect} options={SECENEKLER} />);

    fireEvent.click(screen.getByRole("button", { name: /Model:/ }));
    fireEvent.click(screen.getByText("GPT-OSS 20B"));

    expect(onSelect).toHaveBeenCalledWith("/model agent openrouter/openai/gpt-oss-20b:free");
    expect(screen.queryByRole("listbox")).toBeNull();
  });

  test("yüklenirken durum yazar", () => {
    render(<ModelPicker active="a" busy onSelect={vi.fn()} options={[]} />);
    fireEvent.click(screen.getByRole("button", { name: /Model:/ }));

    expect(screen.getByText("Modeller okunuyor…")).toBeTruthy();
  });

  test("seçenek yoksa ne yapılacağını söyler", () => {
    render(<ModelPicker active="a" onSelect={vi.fn()} options={[]} />);
    fireEvent.click(screen.getByRole("button", { name: /Model:/ }));

    expect(screen.getByText(/Seçilebilir model yok/)).toBeTruthy();
  });

  test("Escape listeyi kapatır", () => {
    render(<ModelPicker active="a" onSelect={vi.fn()} options={SECENEKLER} />);
    fireEvent.click(screen.getByRole("button", { name: /Model:/ }));

    fireEvent.keyDown(document, { key: "Escape" });

    expect(screen.queryByRole("listbox")).toBeNull();
  });

  test("görev büyüklüğüne göre gruplar ve aramayla daraltır", () => {
    const options: ModelOption[] = [
      { deger: "/development uygula openrouter-free openrouter/fast", etiket: "Hızlı", grup: "low" },
      { deger: "/development uygula openrouter-free openrouter/deep", etiket: "Derin", grup: "high" },
    ];
    render(<ModelPicker active="openrouter/fast" onSelect={vi.fn()} options={options} />);
    fireEvent.click(screen.getByRole("button", { name: /Model:/ }));

    expect(screen.getByText("Basit ve hızlı görevler")).toBeTruthy();
    expect(screen.getByText("Büyük ve karmaşık görevler")).toBeTruthy();
    fireEvent.change(screen.getByRole("searchbox", { name: "Model ara" }), { target: { value: "Derin" } });
    expect(screen.queryByText("Hızlı")).toBeNull();
    expect(screen.getByText("Derin")).toBeTruthy();
  });
});
