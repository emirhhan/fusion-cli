import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";
import { resetModelApprovals } from "./modelApprovals";
import { ModelPicker, shortModelName, type ModelOption } from "./ModelPicker";

afterEach(() => { cleanup(); resetModelApprovals(); });

const SECENEKLER: ModelOption[] = [
  { deger: "/model agent gemini_web/main", etiket: "Gemini Web", aciklama: "Tarayıcı oturumu" },
  { deger: "/model agent openrouter/openai/gpt-oss-20b:free", etiket: "GPT-OSS 20B", aciklama: "Ücretsiz" },
];

describe("shortModelName", () => {
  test("sağlayıcı önekini atıp son parçayı bırakır", () => {
    expect(shortModelName("openrouter/openai/gpt-oss-20b:free")).toBe("gpt-oss-20b");
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
    expect(dugme.textContent).toContain("gpt-oss-20b");
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

  test("seçilen seçenek nesnesi olduğu gibi iletilir ve liste kapanır", () => {
    const onSelect = vi.fn();
    render(<ModelPicker active="a" onSelect={onSelect} options={SECENEKLER} />);

    fireEvent.click(screen.getByRole("button", { name: /Model:/ }));
    fireEvent.click(screen.getByText("GPT-OSS 20B"));

    expect(onSelect).toHaveBeenCalledExactlyOnceWith(expect.objectContaining({ deger: "/model agent openrouter/openai/gpt-oss-20b:free" }));
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

    // Tüketilen Esc (preventDefault) Shell'in denetçi kapatmasını tetiklemez (U1-01).
    expect(fireEvent.keyDown(document, { key: "Escape" })).toBe(false);

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
    fireEvent.change(screen.getByRole("combobox", { name: "Model ara" }), { target: { value: "Derin" } });
    expect(screen.queryByText("Hızlı")).toBeNull();
    expect(screen.getByText("Derin")).toBeTruthy();
  });

  /* Bkz. bug: uzun model adı (ör. "nemotron-3-ultra-550b-a55b") seçilince
     yazma kutusundaki yer tutucu alt satıra kayıyordu. Çip; adı kısaltacak
     yapıya (ellipsis'e izin veren min-width:0 barındıran isim span'i) sahip
     olmalı ve düğme kendi max-width'i içinde kalmalı — tam ad yalnız
     `title` özniteliğinde saklanır, düğme metninde taşmaz. */
  test("uzun model adında düğme adı kısaltmaya izin verecek yapıda kalır, tam ad title'da saklanır", () => {
    const uzunAd = "nemotron-3-ultra-550b-a55b-cok-uzun-bir-surum-adi-daha-da-uzasin";
    render(<ModelPicker active={uzunAd} onSelect={vi.fn()} options={[]} />);

    const dugme = screen.getByRole("button", { name: new RegExp(`Model: ${uzunAd}`) });
    expect(dugme.getAttribute("title")).toBe(uzunAd);
    const isimSpani = dugme.querySelector(".model-picker__name");
    expect(isimSpani?.textContent).toBe(shortModelName(uzunAd));
    expect(dugme.className).toContain("model-picker__trigger");
  });
});

describe("shortModelName — kısa çip adı", () => {
  test("boyut eklerini ve :free'yi atar, adın parçası olan boyutu korur", () => {
    expect(shortModelName("nvidia_nim/nvidia/nemotron-3-ultra-550b-a55b")).toBe("nemotron-3-ultra");
    expect(shortModelName("openrouter/nvidia/nemotron-3-super-120b-a12b:free")).toBe("nemotron-3-super");
    expect(shortModelName("nvidia_nim/nvidia/nemotron-3-nano-omni-30b-a3b-reasoning")).toBe("nemotron-3-nano-omni-reasoning");
    expect(shortModelName("nvidia_nim/z-ai/glm-5.3")).toBe("glm-5.3");
  });
});

describe("ModelPicker — araç desteği doğrulanmamış model (U1-45)", () => {
  const BILINMEYEN: ModelOption[] = [
    { deger: "/model agent nim/yeni-model", etiket: "Yeni Model", toolSupport: "unknown" },
    { deger: "/model agent nim/bilinen", etiket: "Bilinen Model", toolSupport: "supported" },
  ];

  test("doğrulanmamış model satır içi onay ister; Vazgeç seçimi uygulamaz", () => {
    const onSelect = vi.fn();
    render(<ModelPicker active="a" onSelect={onSelect} options={BILINMEYEN} />);
    fireEvent.click(screen.getByRole("button", { name: /Model:/ }));
    fireEvent.click(screen.getByRole("option", { name: /Yeni Model/ }));
    expect(onSelect).not.toHaveBeenCalled();
    expect(screen.getByRole("alertdialog", { name: "Yeni Model seçimini onayla" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Vazgeç" }));
    expect(onSelect).not.toHaveBeenCalled();
    expect(screen.queryByRole("alertdialog")).toBeNull();
  });

  test("Yine de seç modeli uygular ve aynı oturumda tekrar sormaz", () => {
    const onSelect = vi.fn();
    render(<ModelPicker active="a" onSelect={onSelect} options={BILINMEYEN} />);
    fireEvent.click(screen.getByRole("button", { name: /Model:/ }));
    fireEvent.click(screen.getByRole("option", { name: /Yeni Model/ }));
    fireEvent.click(screen.getByRole("button", { name: "Yine de seç" }));
    expect(onSelect).toHaveBeenCalledWith(expect.objectContaining({ deger: "/model agent nim/yeni-model" }));
    fireEvent.click(screen.getByRole("button", { name: /Model:/ }));
    fireEvent.click(screen.getByRole("option", { name: /Yeni Model/ }));
    expect(onSelect).toHaveBeenCalledTimes(2);
    expect(screen.queryByRole("alertdialog")).toBeNull();
  });

  test("doğrulanmış model onaysız seçilir", () => {
    const onSelect = vi.fn();
    render(<ModelPicker active="a" onSelect={onSelect} options={BILINMEYEN} />);
    fireEvent.click(screen.getByRole("button", { name: /Model:/ }));
    fireEvent.click(screen.getByRole("option", { name: /Bilinen Model/ }));
    expect(onSelect).toHaveBeenCalledWith(expect.objectContaining({ deger: "/model agent nim/bilinen" }));
  });
});
