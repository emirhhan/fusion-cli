import { useCallback, useEffect, useState } from "react";
import type { ProtocolClient } from "../protocol/client";
import { Button } from "../ui/Button";
import { ProviderList } from "./ProviderList";
import "./ControlPanel.css";

interface ProviderRow { id: string; ad: string; ortam: string; kurulu: boolean }
interface ControlState {
  kok: string;
  model: { agent: string; hakem: string; adaylar: string[]; saglayici: string; yogunluk: string };
  izin: { mod: string; kokle_sinirli: boolean };
  mcp: { ad: string; komut: string }[];
  saglayicilar: ProviderRow[];
  sir_deposu_hatasi?: string | null;
  sir_deposu_hazir: boolean;
  gateway: { durum: string; adres: string; pid?: number };
}

/** Arama anahtarları — bölümlerin çizim sırasıyla aynı sırada. */
const SECTION_KEYS = [
  "model düzeni ajan hakem aday havuz seviye profil",
  "izinler güvenlik çalışma klasörü kök kapsam",
  "sağlayıcılar bağlantılar anahtar api oturum web",
  "yerel gateway openai uyumlu uç nokta cursor cline",
  "mcp sunucuları araç bağlantıları",
] as const;

const permissionLabels: Record<string, string> = {
  ask: "Her işlemde sor",
  auto: "Otomatik uygula",
  plan: "Yalnız planla",
};

function decode(payload: Record<string, unknown>): ControlState {
  if (payload.ok !== true) throw new Error(String(payload.metin ?? "Kontrol durumu alınamadı."));
  return payload as unknown as ControlState;
}

function Definition({ label, value }: { label: string; value: string }) {
  return <div className="control-panel__definition"><dt>{label}</dt><dd>{value}</dd></div>;
}

interface ControlPanelProps {
  client: ProtocolClient;
  /** Çalışma klasörünü değiştir. Verilmezse düğme HİÇ çizilmez. */
  onChangeRoot?: () => void;
  onClose: () => void;
  /**
   * Bir slash komutunu çalıştır. Model düzeni buradan değişir: panel kendi
   * uç noktasını UYDURMAZ, CLI'ın zaten testli olan `/model`, `/level`,
   * `/mode` akışını kullanır. İki yerde ayrı mantık olsaydı biri düzeltilirken
   * öteki eskirdi. Verilmezse değiştirme düğmeleri çizilmez.
   */
  onRunCommand?: (command: string) => void;
}

export function ControlPanel({ client, onChangeRoot, onClose, onRunCommand }: ControlPanelProps) {
  const [state, setState] = useState<ControlState | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [newCandidate, setNewCandidate] = useState({ ad: "", model: "" });

  const reload = useCallback(async () => {
    const payload = await client.request("kontrol.durum", {});
    setState(decode(payload));
  }, [client]);

  useEffect(() => {
    void reload().catch((reason) => setError(String(reason)));
  }, [reload]);

  const perform = async (name: string, data: Record<string, unknown>, success: string) => {
    setBusy(name);
    setError(null);
    try {
      const result = await client.request(name, data);
      if (result.ok !== true) throw new Error(String(result.metin ?? "İşlem tamamlanamadı."));
      setNotice(success);
      await reload();
    } catch (reason) {
      setError(String(reason));
    } finally {
      setBusy(null);
    }
  };

  const aranan = query.trim().toLocaleLowerCase("tr");
  /** Bölüm arama terimiyle eşleşiyor mu? Anahtarlar ekranda görünmeyen eş
   *  anlamlıları da içerir: kullanıcı "anahtar" yazınca sağlayıcılar çıksın. */
  const eslesir = (anahtarlar: string) =>
    !aranan || anahtarlar.toLocaleLowerCase("tr").includes(aranan);
  const bolumler = SECTION_KEYS.filter(eslesir);
  const canAddCandidate = Boolean(newCandidate.ad.trim() && newCandidate.model.trim());

  if (!state) return <main className="control-panel"><p>{error ?? "Kontrol paneli yükleniyor…"}</p></main>;
  const gatewayRunning = state.gateway.durum === "calisiyor";

  return (
    <main className="control-panel">
      <header className="control-panel__header">
        <div><span>Fusion for macOS</span><h2>Kontrol Paneli</h2><p>Modeller, bağlantılar, izinler ve yerel gateway tek görünümde.</p></div>
        <div className="control-panel__header-tools">
          <input
            aria-label="Panelde ara"
            className="control-panel__search"
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Panelde ara"
            type="search"
            value={query}
          />
          <Button onClick={onClose} variant="secondary">Kapat</Button>
        </div>
      </header>
      {(notice || error) && <p className="control-panel__notice" data-error={Boolean(error)} role={error ? "alert" : "status"}>{error ?? notice}</p>}

      <div className="control-panel__layout">
        {eslesir(SECTION_KEYS[0]) && (
        <section className="control-panel__section">
          <div className="control-panel__section-heading"><div><span>Çalışma zamanı</span><h3>Model düzeni</h3></div><i data-online="true">Hazır</i></div>
          <dl>
            <Definition label="Ajan" value={state.model.agent} />
            <Definition label="Hakem" value={state.model.hakem} />
            <Definition label="Adaylar" value={state.model.adaylar.join(" · ") || "Yok"} />
            <Definition label="Yönlendirme" value={`${state.model.saglayici} · ${state.model.yogunluk}`} />
          </dl>
          {onRunCommand && (
            <div className="control-panel__actions">
              <button onClick={() => onRunCommand("/model")} type="button">
                Ajan modelini değiştir
              </button>
              <button onClick={() => onRunCommand("/level")} type="button">
                Düşünme düzeyini değiştir
              </button>
              <button onClick={() => onRunCommand("/mode")} type="button">
                Model profilini değiştir
              </button>
            </div>
          )}

          {onRunCommand && (
            <div className="control-panel__candidates">
              <h4>Aday havuzu</h4>
              {state.model.adaylar.length > 0 && (
                <ul className="control-panel__candidate-list">
                  {state.model.adaylar.map((aday) => (
                    <li key={aday}>
                      <code>{aday}</code>
                      <button
                        aria-label={`${aday} adayını çıkar`}
                        onClick={() => onRunCommand(`/model rm ${aday}`)}
                        type="button"
                      >
                        Çıkar
                      </button>
                    </li>
                  ))}
                </ul>
              )}
              <div className="control-panel__candidate-form">
                <label htmlFor="aday-adi">Aday adı</label>
                <input
                  id="aday-adi"
                  onChange={(event) => setNewCandidate((current) => ({ ...current, ad: event.target.value }))}
                  placeholder="hizli"
                  value={newCandidate.ad}
                />
                <label htmlFor="aday-model">Model kimliği</label>
                <input
                  id="aday-model"
                  onChange={(event) => setNewCandidate((current) => ({ ...current, model: event.target.value }))}
                  placeholder="openrouter/openai/gpt-oss-20b:free"
                  value={newCandidate.model}
                />
                <button
                  disabled={!canAddCandidate}
                  onClick={() => {
                    if (!canAddCandidate) return;
                    onRunCommand(`/model add ${newCandidate.ad.trim()} ${newCandidate.model.trim()}`);
                    setNewCandidate({ ad: "", model: "" });
                  }}
                  type="button"
                >
                  Adayı ekle
                </button>
              </div>
              <small>Havuz `/model` komutuyla yazılır; panel kendi yazma yolunu açmaz.</small>
            </div>
          )}
        </section>
        )}

        {eslesir(SECTION_KEYS[1]) && (
        <section className="control-panel__section">
          <div className="control-panel__section-heading"><div><span>Güvenlik</span><h3>İzinler</h3></div></div>
          <dl>
            <Definition label="Çalışma modu" value={permissionLabels[state.izin.mod] ?? state.izin.mod} />
            <Definition label="Dosya kapsamı" value={state.izin.kokle_sinirli ? "Yalnız proje kökü" : "Onayla genişletilebilir"} />
            <Definition label="Aktif proje" value={state.kok} />
          </dl>
          {onChangeRoot && (
            <div className="control-panel__actions">
              <button onClick={onChangeRoot} type="button">
                Çalışma klasörünü değiştir
              </button>
              <button onClick={() => onRunCommand?.("/security")} type="button">
                İzin modunu değiştir
              </button>
            </div>
          )}
        </section>
        )}

        {eslesir(SECTION_KEYS[2]) && (
        <section className="control-panel__section control-panel__section--wide">
          {state.sir_deposu_hatasi && (
            <p className="control-panel__warning" role="status">{state.sir_deposu_hatasi}</p>
          )}
          <ProviderList client={client} />
        </section>
        )}

        {eslesir(SECTION_KEYS[3]) && (
        <section className="control-panel__section">
          <div className="control-panel__section-heading"><div><span>OpenAI uyumlu</span><h3>Yerel Gateway</h3></div><i data-online={gatewayRunning}>{gatewayRunning ? "Çalışıyor" : "Kapalı"}</i></div>
          <code className="control-panel__endpoint">{state.gateway.adres}</code>
          <p>Cursor, Cline ve yerel araçlar bu uç üzerinden Fusion model yönlendirmesini kullanabilir.</p>
          <Button
            aria-label={gatewayRunning ? "Gateway'i durdur" : "Gateway'i başlat"}
            loading={busy === (gatewayRunning ? "kontrol.gateway_durdur" : "kontrol.gateway_baslat")}
            onClick={() => void perform(gatewayRunning ? "kontrol.gateway_durdur" : "kontrol.gateway_baslat", {}, gatewayRunning ? "Gateway durduruldu." : "Gateway başlatıldı.")}
            variant={gatewayRunning ? "danger" : "primary"}
          >{gatewayRunning ? "Durdur" : "Başlat"}</Button>
        </section>
        )}

        {eslesir(SECTION_KEYS[4]) && (
        <section className="control-panel__section">
          <div className="control-panel__section-heading"><div><span>Araç bağlantıları</span><h3>MCP sunucuları</h3></div><i data-online={state.mcp.length > 0}>{state.mcp.length} bağlı</i></div>
          {state.mcp.length ? <ul>{state.mcp.map((server) => <li key={server.ad}><strong>{server.ad}</strong><code>{server.komut}</code></li>)}</ul> : <p>Henüz MCP sunucusu eklenmedi.</p>}
        </section>
        )}
        {bolumler.length === 0 && (
          <p className="control-panel__empty">"{query.trim()}" için eşleşen bölüm yok.</p>
        )}
      </div>
    </main>
  );
}
