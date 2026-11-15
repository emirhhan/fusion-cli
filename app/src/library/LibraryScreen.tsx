import { useCallback, useEffect, useRef, useState } from "react";
import { assetUrl } from "../platform/assetUrl";
import { selectFiles } from "../platform/dialog";
import { Icon, type IconName } from "../ui/Icon";
import "./LibraryScreen.css";

interface LibraryClient {
  request(name: string, data: Record<string, unknown>): Promise<Record<string, unknown>>;
}

export interface LibraryItem {
  ad: string;
  boyut: number;
  degisim: number;
  kaynak: "uretilen" | "yuklenen" | "gorsel";
  kok: string;
  tur: "gorsel" | "video" | "belge" | "kod" | "diger";
  yol: string;
}

/** Arama kutusunda yazma durduktan sonra çekirdeğe sorulana dek bekleme. */
const SEARCH_DEBOUNCE_MS = 250;

const FILTERS: readonly { id: "" | LibraryItem["tur"]; label: string }[] = [
  { id: "", label: "Tümü" },
  { id: "gorsel", label: "Görseller" },
  { id: "video", label: "Videolar" },
  { id: "belge", label: "Belgeler" },
  { id: "kod", label: "Kod" },
  { id: "diger", label: "Diğer" },
];

const SOURCE_LABEL: Record<LibraryItem["kaynak"], string> = {
  uretilen: "Fusion oluşturdu",
  yuklenen: "Yüklendi",
  gorsel: "Görsel üretimi",
};

const KIND_ICON: Record<LibraryItem["tur"], IconName> = {
  gorsel: "image",
  video: "video",
  belge: "files",
  kod: "terminal",
  diger: "files",
};

export function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

async function revealInFolder(path: string): Promise<void> {
  const { revealItemInDir } = await import("@tauri-apps/plugin-opener");
  await revealItemInDir(path);
}

interface LibraryScreenProps {
  /** Çekirdek bağlı değilken (hiç sohbet açılmadı) `null`. */
  client: LibraryClient | null;
  chooseFiles?: () => Promise<string[]>;
  reveal?: (path: string) => Promise<void>;
  toUrl?: (path: string) => string | null;
  /** Bölüm görünür olduğunda liste tazelenir (tur bittiğinde yeni dosyalar gelir). */
  visible?: boolean;
}

export function LibraryScreen({
  client,
  chooseFiles = selectFiles,
  reveal = revealInFolder,
  toUrl = assetUrl,
  visible = true,
}: LibraryScreenProps) {
  const [items, setItems] = useState<LibraryItem[]>([]);
  const [total, setTotal] = useState(0);
  const [kind, setKind] = useState<"" | LibraryItem["tur"]>("");
  const [query, setQuery] = useState("");
  // Liste ve işlem hataları ayrıdır: başarılı bir yenileme, az önce başarısız olan
  // yüklemenin hatasını silmemeli (ölçüldü, 29 Ekim).
  const [listError, setListError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const error = actionError ?? listError;
  const [loading, setLoading] = useState(false);
  // Arama kutusu her tuşta çekirdeğe gitmesin: yazma durunca sorgulanan değer güncellenir.
  const [debouncedQuery, setDebouncedQuery] = useState("");
  // Son istek kazanır: yavaş eski yanıt yeni süzgecin listesini ezmesin.
  const latestRequest = useRef(0);

  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedQuery(query), SEARCH_DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [query]);

  const load = useCallback(async () => {
    if (!client) return;
    const requestId = ++latestRequest.current;
    setLoading(true);
    try {
      const result = await client.request("kitaplik.liste", { tur: kind, sorgu: debouncedQuery });
      if (requestId !== latestRequest.current) return;
      if (result.ok) {
        setItems(Array.isArray(result.dosyalar) ? (result.dosyalar as LibraryItem[]) : []);
        setTotal(typeof result.toplam === "number" ? result.toplam : 0);
        setListError(null);
      } else {
        setListError(typeof result.metin === "string" ? result.metin : "Kitaplık okunamadı.");
      }
    } catch {
      if (requestId === latestRequest.current) setListError("Kitaplık okunamadı. Yeniden dene.");
    } finally {
      if (requestId === latestRequest.current) setLoading(false);
    }
  }, [client, kind, debouncedQuery]);

  useEffect(() => {
    if (visible) void load();
  }, [load, visible]);

  /** Başarıda `null`, hatada kullanıcıya gösterilecek metin döner. */
  const act = async (name: string, data: Record<string, unknown>, fallback: string): Promise<string | null> => {
    if (!client) return fallback;
    try {
      const result = await client.request(name, data);
      if (result.ok) return null;
      return typeof result.metin === "string" ? result.metin : fallback;
    } catch {
      return fallback;
    }
  };

  const upload = async () => {
    let paths: string[];
    try {
      paths = await chooseFiles();
    } catch {
      setActionError("Dosya seçici açılamadı.");
      return;
    }
    if (paths.length === 0) return;
    setActionError(null);
    const failures: string[] = [];
    for (const yol of paths) {
      const failure = await act("kitaplik.ekle", { yol }, "Dosya eklenemedi.");
      if (failure) failures.push(failure);
    }
    if (failures.length === 1) setActionError(failures[0]);
    else if (failures.length > 1) setActionError(`${failures.length} dosya eklenemedi. İlk neden: ${failures[0]}`);
    await load();
  };

  const remove = async (yol: string) => {
    setActionError(null);
    const failure = await act("kitaplik.kaldir", { yol }, "Kayıt kaldırılamadı.");
    if (failure) setActionError(failure);
    await load();
  };

  return (
    <div className="library">
      <header className="library__header" data-tauri-drag-region>
        <h1>Kitaplık</h1>
        <button className="library__upload" disabled={!client} onClick={() => void upload()} type="button">
          <Icon name="attach" size={16} /> Dosya yükle
        </button>
      </header>
      <div className="library__tools">
        <div aria-label="Tür süzgeci" className="library__filters" role="tablist">
          {FILTERS.map((filter) => (
            <button aria-selected={kind === filter.id} key={filter.label} onClick={() => setKind(filter.id)} role="tab" type="button">
              {filter.label}
            </button>
          ))}
        </div>
        <label className="library__search">
          <Icon name="search" size={16} />
          <input aria-label="Kitaplıkta ara" onChange={(event) => setQuery(event.target.value)} placeholder="Ara" type="search" value={query} />
        </label>
      </div>
      {error && <p className="library__error" role="alert">{error}</p>}
      {!client ? (
        <p className="library__empty">Kitaplığı görmek için Home'da bir sohbet aç.</p>
      ) : items.length === 0 ? (
        <p className="library__empty">
          {loading ? "Yükleniyor…" : query || kind ? "Bu süzgece uyan dosya yok." : "Henüz dosya yok. Fusion'ın oluşturduğu ve senin yüklediğin dosyalar burada görünür."}
        </p>
      ) : (
        <>
          <ul aria-label="Kitaplık dosyaları" className="library__grid">
            {items.map((item) => {
              const preview = item.tur === "gorsel" ? toUrl(item.yol) : null;
              return (
                <li className="library__card" key={item.yol}>
                  <div className="library__thumb">
                    {preview ? <img alt="" height={120} loading="lazy" src={preview} width={160} /> : <Icon name={KIND_ICON[item.tur]} size={28} />}
                  </div>
                  <p className="library__name" title={item.yol}>{item.ad}</p>
                  <p className="library__meta">{SOURCE_LABEL[item.kaynak]} · {formatSize(item.boyut)}</p>
                  <div className="library__actions">
                    <button onClick={() => void reveal(item.yol).catch(() => setActionError("Klasör açılamadı."))} type="button">Klasörde göster</button>
                    {item.kaynak !== "gorsel" && (
                      <button aria-label={`${item.ad} kaydını kaldır`} onClick={() => void remove(item.yol)} type="button">Kaldır</button>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
          {total > items.length && <p className="library__meta">{total} dosyadan ilk {items.length} tanesi gösteriliyor; aramayla daralt.</p>}
        </>
      )}
    </div>
  );
}
