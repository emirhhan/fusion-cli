import { open } from "@tauri-apps/plugin-dialog";

/** İşletim sisteminin yerel klasör seçicisini açar. */
export async function selectDirectory(defaultPath?: string): Promise<string | null> {
  const selected = await open({
    defaultPath: defaultPath || undefined,
    directory: true,
    multiple: false,
    title: "Fusion çalışma klasörünü seç",
  });
  return typeof selected === "string" ? selected : null;
}

/** Kits'in proje listesine eklenecek klasörü seçer. */
export async function selectProjectFolder(): Promise<string | null> {
  const selected = await open({ directory: true, multiple: false, title: "Kits'e proje klasörü ekle" });
  return typeof selected === "string" ? selected : null;
}

/** Ataç düğmesi için bir veya daha fazla yerel dosya seçer. */
export async function selectFiles(defaultPath?: string): Promise<string[]> {
  const selected = await open({
    defaultPath: defaultPath || undefined,
    directory: false,
    multiple: true,
    title: "Fusion'a dosya ekle",
  });
  if (Array.isArray(selected)) return selected;
  return typeof selected === "string" ? [selected] : [];
}

/**
 * Görseli "İndir" ile kaydetmek için yerel kayıt penceresini açar.
 *
 * Üretilen görseller kendiliğinden diske/Finder'a inmez; kullanıcı yalnız bu
 * pencerede seçtiği yere kaydeder. İptalde `null` döner.
 */
export async function saveImageAs(defaultName: string): Promise<string | null> {
  const { save } = await import("@tauri-apps/plugin-dialog");
  const selected = await save({
    defaultPath: defaultName,
    filters: [{ extensions: ["png", "jpg", "jpeg"], name: "Görsel" }],
    title: "Görseli kaydet",
  });
  return typeof selected === "string" ? selected : null;
}

/** Kits ekrana bakmak istediğinde her seferinde kullanıcıya yerel pencereyle sorar. */
export async function askComputerAccess(reason: string): Promise<boolean> {
  const { ask } = await import("@tauri-apps/plugin-dialog");
  const neden = reason.trim() ? `\n\nKits'in belirttiği neden (Fusion doğrulamaz): ${reason.trim()}` : "";
  return ask(
    "Kits ekranının bir görüntüsünü ve öndeki pencerenin öğelerini okumak istiyor. " +
      "Tıklama ya da yazma yapamaz; yalnız bakar. Ekrandaki anahtar ve parola benzeri metinler gizlenir." + neden,
    { title: "Kits bilgisayarına bakmak istiyor", kind: "warning", okLabel: "İzin ver", cancelLabel: "Reddet" },
  );
}

/** Kits bir Kit adına kullanıcının Chrome'unu (Fusion eklentisi) kullanmak istediğinde sorar.
 * Okuma eylemleri Kits açık kaldığı sürece bir kez, etkileşim eylemleri her seferinde sorulur. */
export async function askKitsBrowserAccess(summary: string, interactive: boolean): Promise<boolean> {
  const { ask } = await import("@tauri-apps/plugin-dialog");
  const scope = interactive
    ? "Bu eylem sayfayı değiştirebilir; her seferinde ayrıca sorulur."
    : "Yalnız okur; izin verirsen okuma istekleri Kits açık kaldığı sürece tekrar sorulmaz.";
  return ask(
    `${summary}\n\n${scope} Sayfadaki anahtar ve parola benzeri metinler Kits'e gönderilmez; ekran görüntüsü taşınmaz.`,
    { title: "Kits Chrome'unu kullanmak istiyor", kind: "warning", okLabel: "İzin ver", cancelLabel: "Reddet" },
  );
}

/** Kits'in sesli konuşması mikrofonu ilk kez istediğinde yerel pencereyle sorar. İzin, Kits açık kaldığı sürece hatırlanır. */
export async function askMicrophoneAccess(): Promise<boolean> {
  const { ask } = await import("@tauri-apps/plugin-dialog");
  return ask(
    "Kits sesli konuşma için mikrofonunu dinlemek istiyor. Tanıma bu Mac'te yapılır; ses dışarı çıkmaz. " +
      "İzin verirsen Kits açık kaldığı sürece tekrar sorulmaz.",
    { title: "Kits mikrofonunu kullanmak istiyor", kind: "warning", okLabel: "İzin ver", cancelLabel: "Reddet" },
  );
}
