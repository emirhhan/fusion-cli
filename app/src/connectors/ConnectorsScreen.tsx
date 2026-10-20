import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ProtocolClient } from "../protocol/client";
import { Button } from "../ui/Button";
import { PageHeader } from "../ui/PageHeader";
import { ConnectorIcon } from "./ConnectorIcon";
import { ConnectorSetupForm } from "./ConnectorSetupForm";
import { ConnectorDialog } from "./ConnectorDialog";
import { McpToolCatalog } from "./McpToolCatalog";
import { CustomConnectorWizard } from "./CustomConnectorWizard";
import {
  addPayloadFor,
  allConnectors,
  catalogConnectors,
  featuredConnectors,
  requiredRunner,
  type CatalogEntry,
  type ConnectorTransport,
} from "./catalog";
import "./ConnectorsScreen.css";

/** Bağlı MCP sunucusunun `baglanti.listele`'den gelen satırı. */
interface ConnectorRow {
  ad: string;
  guven?: "unreviewed" | "trusted" | "revoked";
  inceleme_kimligi?: string | null;
  argumanlar?: string[];
  arac_sayisi?: number;
  durum?: string;
  komut: string;
  mesaj?: string | null;
  /** Satırın taşıması. `hosted` KATALOGDA yoktur ama çekirdek onu döndürür:
   *  barındırmalı bağlantılar ayrı depoda yaşar ve ayrı uçtan silinir. Tipin
   *  bunu taşımaması, silme hatasını derleyiciden gizlemişti. */
  tasima?: ConnectorTransport | "hosted";
  url?: string;
}

interface RpcResult {
  durum?: string;
  mesaj?: string | null;
  metin?: string;
  oauth_donus_adresi?: string;
  ok?: boolean;
  sunucular?: ConnectorRow[];
}

const STATE_LABELS: Record<string, string> = {
  bagli: "Bağlı",
  backoff: "Yeniden deneme bekliyor",
  degraded: "Kısmen kullanılabilir",
  parked: "Kullanıcı işlemi gerekiyor",
  giris_bekleniyor: "Giriş bekleniyor",
  // Sunucu sağlam, yalnız kullanıcının girişini bekliyor: "hata" DEĞİL.
  giris_gerekli: "Giriş gerekli",
  kopya: "Kopya",
  hata: "Bağlantı hatası",
  kapali: "Bağlı değil",
  yapilandirildi: "Test edilmedi",
  zaman_asimi: "Zaman aşımı",
};

type TabId = "kesfet" | "bagli";

interface HostedProvider {
  adres: string;
  ad: string;
  hazir: boolean;
  id: string;
}

interface HostedResult {
  adres: string;
  ad: string;
  mcp_adresi: string;
  saglayici: string;
}

const CUSTOM_EMPTY = {
  ad: "",
  client_id: "",
  kapsamlar: "",
  komut: "",
  saglayici: "",
  tasima: "stdio" as ConnectorTransport | "hosted",
  token: "",
  url: "",
};

export function ConnectorsScreen({
  client,
  onClose,
}: {
  client: ProtocolClient;
  onClose: () => void;
}) {
  const owner = useRef({ client, alive: true, load: 0, action: 0 });
  if (owner.current.client !== client) owner.current = { client, alive: true, load: 0, action: 0 };
  const [storedRows, setRows] = useState<ConnectorRow[]>([]);
  const [rowsClient, setRowsClient] = useState(client);
  const rows = rowsClient === client ? storedRows : [];
  useEffect(() => {
    const current = owner.current;
    current.alive = true;
    return () => { current.alive = false; };
  }, [client]);
  const [tab, setTab] = useState<TabId>("kesfet");
  const [query, setQuery] = useState("");
  const [busyEntry, setBusyEntry] = useState<{ owner: typeof owner.current; key: string | null } | null>(null);
  const busy = busyEntry?.owner === owner.current ? busyEntry.key : null;
  const [notice, setNotice] = useState<string | null>(null);
  const [showCustom, setShowCustom] = useState(false);
  const [catalog, setCatalog] = useState<{ client: ProtocolClient; server: string } | null>(null);
  const [setupEntry, setSetupEntry] = useState<CatalogEntry | null>(null);
  const [custom, setCustom] = useState(CUSTOM_EMPTY);
  // Sağlayıcı-barındırmalı bağlantı: araçlar Fusion'da değil, kullanıcının zaten
  // giriş yaptığı web sağlayıcısının connector ekranında yaşar.
  const [providers, setProviders] = useState<HostedProvider[] | null>(null);
  // OAuth dönüş adresi sunucudan gelir: port sabittir ama arayüz onu
  // TEKRARLAMAZ — iki yerde yazılan bir sabit zamanla ayrışır.
  const [oauthReturn, setOauthReturn] = useState("");

  const load = useCallback(async () => {
    const current = owner.current, sequence = ++current.load;
    try {
      const result = (await client.request("baglanti.listele", {})) as RpcResult;
      if (owner.current !== current || !current.alive || sequence !== current.load) return;
      if (result?.ok !== true) throw new Error("Bağlantılar okunamadı.");
      setRows(result.sunucular ?? []);
      setRowsClient(client);
      setOauthReturn(result.oauth_donus_adresi ?? "");
    } catch {
      if (owner.current === current && current.alive && sequence === current.load) setNotice("Bağlantılar okunamadı. Yeniden deneyebilirsin.");
    }
  }, [client]);

  useEffect(() => {
    void load().catch(() => setNotice("Bağlantılar okunamadı."));
  }, [load]);

  // Giriş bekleyen bağlantı varsa durumu kısa aralıkla tazele (OAuth tamamlanınca
  // ekran kendiliğinden "Bağlı"ya döner).
  useEffect(() => {
    if (!rows.some((row) => row.durum === "giris_bekleniyor" || row.durum === "backoff")) return;
    const timer = window.setInterval(() => void load(), 1200);
    return () => window.clearInterval(timer);
  }, [load, rows]);

  // Tür "hosted" seçilince sağlayıcılar okunur. Liste veriden gelir: hangi
  // sağlayıcının hazır olduğunu arayüz TAHMİN ETMEZ.
  useEffect(() => {
    if (custom.tasima !== "hosted" || providers !== null) return;
    let iptal = false;
    void (async () => {
      try {
        const result = (await client.request("baglanti.saglayicilar", {})) as {
          ok?: boolean;
          saglayicilar?: HostedProvider[];
        };
        if (!iptal && result?.ok) setProviders(result.saglayicilar ?? []);
      } catch {
        if (!iptal) setProviders([]);
      }
    })();
    return () => {
      iptal = true;
    };
  }, [client, custom.tasima, providers]);

  // İlk hazır sağlayıcı kendiliğinden seçilir: tek seçenek varken kullanıcıyı
  // ayrıca tıklatmak gereksiz bir adımdır.
  useEffect(() => {
    if (custom.tasima !== "hosted" || custom.saglayici) return;
    const ilk = providers?.find((item) => item.hazir);
    if (ilk) setCustom((c) => ({ ...c, saglayici: ilk.id }));
  }, [custom.saglayici, custom.tasima, providers]);

  const run = useCallback(
    async (name: string, data: Record<string, unknown>, key: string) => {
      const current = owner.current, sequence = ++current.action;
      const isCurrent = () => owner.current === current && current.alive && sequence === current.action;
      setBusyEntry({ owner: current, key });
      setNotice(null);
      try {
        const result = (await client.request(name, data)) as RpcResult;
        if (!isCurrent()) return null;
        setNotice(result?.metin ?? result?.mesaj ?? null);
        await load();
        return isCurrent() ? result : null;
      } catch {
        if (isCurrent()) setNotice("Bağlantı işlemi tamamlanamadı.");
        return null;
      } finally {
        if (isCurrent()) setBusyEntry({ owner: current, key: null });
      }
    },
    [client, load],
  );

  const rowByName = useMemo(() => {
    const map = new Map<string, ConnectorRow>();
    for (const row of rows) map.set(row.ad, row);
    return map;
  }, [rows]);

  // Katalogdan bağla: önce tanımı ekle, remote+OAuth ise girişi hemen başlat.
  const connectCatalog = useCallback(
    async (entry: CatalogEntry) => {
      const existing = rowByName.get(entry.id);
      if (!existing) {
        if (entry.setup?.length) {
          setSetupEntry(entry);
          return;
        }
        await run("baglanti.ekle", addPayloadFor(entry), `add:${entry.id}`);
        return;
      }
      // "Giriş gerekli" durumu backend'den gelir; katalog OAuth işaretlemese bile
      // sunucunun kendisi giriş istediğini söylemiştir.
      if (
        entry.transport === "streamable_http" &&
        (entry.oauth || existing.durum === "giris_gerekli")
      ) {
        await run("baglanti.giris", { ad: entry.id }, `login:${entry.id}`);
      }
    },
    [rowByName, run],
  );

  const filteredCatalog = useMemo(() => {
    const q = query.trim().toLocaleLowerCase("tr");
    if (!q) return catalogConnectors;
    return catalogConnectors.filter(
      (e) =>
        e.label.toLocaleLowerCase("tr").includes(q) ||
        e.description.toLocaleLowerCase("tr").includes(q) ||
        e.category.toLocaleLowerCase("tr").includes(q),
    );
  }, [query]);

  const connectedRows = useMemo(
    () => rows.filter((row) => row.durum === "bagli"),
    [rows],
  );

  // Kilit DÜĞME BAŞINA. Tek bir `busy` bayrağı bütün ekranı kilitliyordu:
  // uzun süren bir istek (sağlayıcı panelini açmak, kullanıcı pencereyi
  // kapatana kadar sürer) boyunca hiçbir düğmeye basılamıyor ve ekran donmuş
  // görünüyordu. İstekler birbirinden bağımsız; birlikte kilitlemek gereksiz.
  const mesgul = (key: string) => busy === key;
  const eklemeMesgul = busy?.startsWith("add:") ?? false;

  /**
   * Barındırmalı bağlantıyı ekle ve KULLANICIYI İŞİN İÇİNDEN ÇIKAR.
   *
   * Ölçülmüş akış şuydu: kullanıcı adresi yazıyor, sağlayıcıyı seçiyor, Ekle'ye
   * basıyor ve altta yeşil bir blok açılıp "şu adresi sağlayıcının MCP alanına
   * yapıştır" diyordu — yani kullanıcının az önce YAZDIĞI adresi geri veriyordu.
   * Artık adres panoya kopyalanır, sağlayıcının connector ekranı doğrudan
   * açılır ve doğrulama kendiliğinden denenir.
   */
  const submitHosted = async () => {
    const result = (await run(
      "baglanti.saglayici_ekle",
      { ad: custom.ad, url: custom.url, saglayici: custom.saglayici },
      "add:hosted",
    )) as (HostedResult & { ok?: boolean }) | undefined;
    if (!result?.ok) return;
    setCustom((c) => ({ ...CUSTOM_EMPTY, saglayici: c.saglayici, tasima: "hosted" }));
    // Pano yazımı başarısız olabilir (izin, odak); adres yine ekranda durur.
    const kopyalandi = await navigator.clipboard
      ?.writeText(result.mcp_adresi)
      .then(() => true, () => false);
    setNotice(
      kopyalandi
        ? "Adres panoya kopyalandı. Sağlayıcının connector ekranı açılıyor…"
        : "Sağlayıcının connector ekranı açılıyor…",
    );
    await run("baglanti.panel_ac", { saglayici: result.saglayici }, "panel:hosted");
    // Panel kapandığında doğrulama KENDİLİĞİNDEN denenir: kullanıcının ayrıca
    // bir düğmeye basması gereken bir adım değil.
    await run("baglanti.saglayici_dogrula", { ad: result.ad }, "dogrula:hosted");
  };

  const submitCustom = async () => {
    if (custom.tasima === "hosted") {
      await submitHosted();
      return;
    }
    const payload =
      custom.tasima === "stdio"
        ? { ad: custom.ad, komut: custom.komut }
        : {
            ad: custom.ad,
            tasima: custom.tasima,
            url: custom.url,
            kapsamlar: custom.kapsamlar,
            client_id: custom.client_id,
            token: custom.token,
          };
    const result = await run("baglanti.ekle", payload, "add:custom");
    if (result?.ok) {
      setCustom(CUSTOM_EMPTY);
      setShowCustom(false);
    }
  };

  const submitSetup = async (values: Readonly<Record<string, string>>) => {
    if (!setupEntry) return;
    const result = await run(
      "baglanti.ekle",
      addPayloadFor(setupEntry, values),
      `add:${setupEntry.id}`,
    );
    if (result?.ok) setSetupEntry(null);
  };

  const entryLabel = (id: string): string =>
    allConnectors.find((e) => e.id === id)?.label ?? id;

  return (
    <main className="connectors">
      <PageHeader
        actions={
          <>
            <input
              aria-label="Bağlantı ara"
              className="connectors__search"
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Bağlantı ara"
              type="search"
              value={query}
            />
            <Button onClick={() => setShowCustom((open) => !open)} variant="primary">
              Ekle
            </Button>
            <Button onClick={onClose} variant="secondary">
              Kapat
            </Button>
          </>
        }
        description="Fusion'ı kullandığın araçlara bağla. Uygulamalar MCP üzerinden çalışır; özel sunucuyu Ekle ile tanımla."
        title="Uygulamalar"
      />

      {notice && (
        <p className="connectors__notice" role="status">
          {notice}
          <button type="button" onClick={() => void load()}>Yeniden dene</button>
        </p>
      )}

      {setupEntry && (
        <ConnectorDialog label={`${setupEntry.label} bağlantısını kur`} onClose={() => setSetupEntry(null)}>
        <ConnectorSetupForm
          busy={eklemeMesgul}
          entry={setupEntry}
          onCancel={() => setSetupEntry(null)}
          onSubmit={(values) => void submitSetup(values)}
        />
        {notice && <p role="status">{notice}</p>}
        </ConnectorDialog>
      )}

      {catalog?.client === client && <McpToolCatalog client={client} server={catalog.server} onClose={() => setCatalog(null)} />}
      {showCustom && (
        <ConnectorDialog label="Özel MCP sunucusu ekle" onClose={() => setShowCustom(false)}>
          <CustomConnectorWizard
            deger={custom}
            mesgul={eklemeMesgul}
            oauthDonusAdresi={oauthReturn}
            onCancel={() => setShowCustom(false)}
            onChange={setCustom}
            onSubmit={() => void submitCustom()}
            saglayicilar={providers}
          />
          {notice && <p role="status">{notice}</p>}
        </ConnectorDialog>
      )}

      <div className="connectors__tabs" role="tablist">
        <button
          aria-selected={tab === "kesfet"}
          className="connectors__tab"
          onClick={() => setTab("kesfet")}
          role="tab"
          type="button"
        >
          Keşfet
        </button>
        <button
          aria-selected={tab === "bagli"}
          className="connectors__tab"
          onClick={() => setTab("bagli")}
          role="tab"
          type="button"
        >
          Bağlı{connectedRows.length > 0 ? ` · ${connectedRows.length}` : ""}
        </button>
      </div>

      {tab === "kesfet" ? (
        <>
          {!query && (
            <section aria-label="Popüler bağlantılar" className="connectors__featured">
              {featuredConnectors.map((entry) => {
                const row = rowByName.get(entry.id);
                const connected = row?.durum === "bagli";
                const pending = row?.durum === "giris_bekleniyor";
                return (
                  <article className="connectors__banner" key={entry.id}>
                    <ConnectorIcon entry={entry} size={44} />
                    <div className="connectors__banner-body">
                      <strong>{entry.label}</strong>
                      <p>{entry.description}</p>
                    </div>
                    <button
                      className="connectors__connect"
                      data-connected={connected}
                      disabled={mesgul(`add:${entry.id}`) || connected || pending}
                      onClick={() => void connectCatalog(entry)}
                      type="button"
                    >
                      {connected ? "Bağlı" : pending ? "Giriş bekleniyor…" : "Bağlan"}
                    </button>
                  </article>
                );
              })}
            </section>
          )}

          {/* ChatGPT'nin Uygulamalar dizini: simge, ad ve tek satır açıklama taşıyan
              kartlar ızgarası. Tablo ("Tür / Durum" sütunları) teknik bir liste gibi
              duruyordu; tür bilgisi kartın alt satırına indi. */}
          <ul aria-label="Uygulamalar" className="connectors__grid">
            {filteredCatalog.map((entry) => {
              const row = rowByName.get(entry.id);
              const connected = row?.durum === "bagli";
              const pending = row?.durum === "giris_bekleniyor";
              const loginNeeded = row?.durum === "giris_gerekli";
              const runner = requiredRunner(entry);
              const tur = [
                entry.transport === "stdio" ? "Yerel" : "Uzak",
                entry.oauth ? "OAuth" : "",
                runner ? `${runner} gerekir` : "",
              ].filter(Boolean).join(" · ");
              return (
                <li className="connectors__app" data-connected={connected} key={entry.id}>
                  <ConnectorIcon entry={entry} size={40} />
                  <div className="connectors__app-body">
                    <strong>{entry.label}</strong>
                    <p>{entry.description}</p>
                    <small>
                      {connected ? "✓ Bağlı" : pending ? "Giriş bekleniyor" : loginNeeded ? "Giriş gerekli" : tur}
                    </small>
                  </div>
                  <button
                    className="connectors__connect"
                    data-connected={connected}
                    disabled={mesgul(`add:${entry.id}`) || connected || pending}
                    onClick={() => void connectCatalog(entry)}
                    type="button"
                  >
                    {connected ? "Bağlı" : entry.setup?.length ? "Kur" : "Bağlan"}
                  </button>
                </li>
              );
            })}
            {filteredCatalog.length === 0 && (
              <li className="connectors__empty">
                "{query}" için katalogda eşleşme yok. Özel sunucuyu Ekle ile tanımlayabilirsin.
              </li>
            )}
          </ul>
        </>
      ) : (
        <section aria-label="Bağlı sunucular" className="connectors__connected">
          {rows.length === 0 ? (
            <p className="connectors__empty-block">
              Henüz bağlantı yok. Keşfet sekmesinden bir sunucuya bağlan.
            </p>
          ) : (
            <ul className="connectors__list">
              {rows.map((row) => {
                const remote = row.tasima === "streamable_http";
                const hosted = row.tasima === "hosted";
                const pending = row.durum === "giris_bekleniyor";
                return (
                  <li className="connectors__row" data-state={row.durum} key={row.ad}>
                    <div className="connectors__row-main">
                      <strong>{entryLabel(row.ad)}</strong>
                      <span className="connectors__status">
                        {STATE_LABELS[row.durum ?? "yapilandirildi"] ?? "Durum bilinmiyor"}
                      </span>
                      {row.durum === "bagli" && (
                        <small>{row.arac_sayisi ?? 0} araç</small>
                      )}
                    </div>
                    <code>
                  {/* `hosted` satırı komut taşımaz; dizi eksik gelse bile
                      ekran çökmemeli (ölçüldü: TypeError bütün sayfayı
                      boşaltıyordu). */}
                  {row.url ? row.url : [row.komut, ...(row.argumanlar ?? [])].join(" ")}
                </code>
                    {row.mesaj && (
                      <p className="connectors__row-error" role="status">
                        {row.mesaj}
                      </p>
                    )}
                    {row.tasima !== "hosted" && <p>
                      Kaynak güveni: {row.guven === "trusted" ? "İncelendi" : row.guven === "revoked" ? "Geri alındı" : "İncelenmedi"}
                    </p>}
                    <div className="connectors__row-actions">
                      {!hosted && <button type="button" onClick={() => setCatalog({ client, server: row.ad })}>Araçları gör</button>}
                      {row.tasima !== "hosted" && row.guven !== "trusted" && row.inceleme_kimligi && <button
                        type="button" disabled={mesgul(`trust:${row.ad}`)}
                        onClick={() => void run("baglanti.guven", { ad: row.ad, guven: "trusted", inceleme_kimligi: row.inceleme_kimligi }, `trust:${row.ad}`)}>
                        Bu kaynağın salt okuma bildirimlerine güven
                      </button>}
                      {row.tasima !== "hosted" && row.guven === "trusted" && <button
                        type="button" disabled={mesgul(`trust:${row.ad}`)}
                        onClick={() => void run("baglanti.guven", { ad: row.ad, guven: "revoked" }, `trust:${row.ad}`)}>
                        Güveni geri al
                      </button>}

                      {remote && row.durum !== "bagli" && (
                        <button
                          disabled={mesgul(`login:${row.ad}`) || pending}
                          onClick={() => void run("baglanti.giris", { ad: row.ad }, `login:${row.ad}`)}
                          type="button"
                        >
                          {pending
                            ? "Giriş bekleniyor…"
                            : row.durum === "giris_gerekli"
                              ? "Bağlan"
                              : "Giriş yap"}
                        </button>
                      )}
                      <button
                        disabled={mesgul(`test:${row.ad}`) || pending}
                        onClick={() => void run("baglanti.dogrula", { ad: row.ad }, `test:${row.ad}`)}
                        type="button"
                      >
                        Test et
                      </button>
                      {remote && row.durum === "bagli" && (
                        <button
                          disabled={mesgul(`logout:${row.ad}`)}
                          onClick={() => void run("baglanti.cikis", { ad: row.ad }, `logout:${row.ad}`)}
                          type="button"
                        >
                          Çıkış yap
                        </button>
                      )}
                      <button
                        disabled={mesgul(`remove:${row.ad}`)}
                        onClick={() =>
                          // Barındırmalı bağlantı AYRI bir depoda yaşar
                          // (`config.hosted_connectors`) ve ayrı uçtan silinir.
                          // Ölçülen hata: her satır için `baglanti.sil`
                          // çağrılıyordu; uç barındırmalı kaydı bulamayıp
                          // "'X' adlı bağlantı yok" diyor, satır ekranda
                          // kalıyor ve kullanıcı silemediğini görüyordu.
                          void run(
                            hosted ? "baglanti.saglayici_sil" : "baglanti.sil",
                            { ad: row.ad },
                            `remove:${row.ad}`,
                          )
                        }
                        type="button"
                      >
                        Kaldır
                      </button>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </section>
      )}
    </main>
  );
}
