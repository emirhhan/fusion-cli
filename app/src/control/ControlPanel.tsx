import { useCallback, useEffect, useState } from "react";
import type { ProtocolClient } from "../protocol/client";
import { Button } from "../ui/Button";
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

export function ControlPanel({ client, onClose }: { client: ProtocolClient; onClose: () => void }) {
  const [state, setState] = useState<ControlState | null>(null);
  const [secrets, setSecrets] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState<string | null>(null);

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

  if (!state) return <main className="control-panel"><p>{error ?? "Kontrol paneli yükleniyor…"}</p></main>;
  const gatewayRunning = state.gateway.durum === "calisiyor";

  return (
    <main className="control-panel">
      <header className="control-panel__header">
        <div><span>Fusion for macOS</span><h2>Kontrol Paneli</h2><p>Modeller, bağlantılar, izinler ve yerel gateway tek görünümde.</p></div>
        <Button onClick={onClose} variant="secondary">Kapat</Button>
      </header>
      {(notice || error) && <p className="control-panel__notice" data-error={Boolean(error)} role={error ? "alert" : "status"}>{error ?? notice}</p>}

      <div className="control-panel__layout">
        <section className="control-panel__section">
          <div className="control-panel__section-heading"><div><span>Çalışma zamanı</span><h3>Model düzeni</h3></div><i data-online="true">Hazır</i></div>
          <dl>
            <Definition label="Ajan" value={state.model.agent} />
            <Definition label="Hakem" value={state.model.hakem} />
            <Definition label="Adaylar" value={state.model.adaylar.join(" · ") || "Yok"} />
            <Definition label="Yönlendirme" value={`${state.model.saglayici} · ${state.model.yogunluk}`} />
          </dl>
        </section>

        <section className="control-panel__section">
          <div className="control-panel__section-heading"><div><span>Güvenlik</span><h3>İzinler</h3></div></div>
          <dl>
            <Definition label="Çalışma modu" value={permissionLabels[state.izin.mod] ?? state.izin.mod} />
            <Definition label="Dosya kapsamı" value={state.izin.kokle_sinirli ? "Yalnız proje kökü" : "Onayla genişletilebilir"} />
            <Definition label="Aktif proje" value={state.kok} />
          </dl>
        </section>

        <section className="control-panel__section control-panel__section--wide">
          <div className="control-panel__section-heading"><div><span>Kimlik bilgileri</span><h3>Sağlayıcılar</h3><p>Anahtarlar sistem anahtarlığında şifrelenir; değerleri arayüze geri okunmaz.</p></div><i data-online={state.sir_deposu_hazir && !state.sir_deposu_hatasi}>{state.sir_deposu_hatasi ? "Anahtarlık okunamadı" : state.sir_deposu_hazir ? "Anahtarlık hazır" : "Anahtarlık yok"}</i></div>
          {state.sir_deposu_hatasi && (
            <p className="control-panel__warning" role="status">{state.sir_deposu_hatasi}</p>
          )}
          <div className="control-panel__providers">
            {state.saglayicilar.map((provider) => (
              <div className="control-panel__provider" key={provider.id}>
                <div><strong>{provider.ad}</strong><small>{provider.ortam}</small></div>
                <span data-configured={provider.kurulu}>{provider.kurulu ? "Yapılandırıldı" : "Anahtar gerekli"}</span>
                <input
                  aria-label={`${provider.ad} API anahtarı`}
                  autoComplete="off"
                  disabled={!state.sir_deposu_hazir}
                  onChange={(event) => setSecrets((current) => ({ ...current, [provider.id]: event.target.value }))}
                  placeholder="Yeni anahtar"
                  type="password"
                  value={secrets[provider.id] ?? ""}
                />
                <Button
                  aria-label={`${provider.ad} anahtarını kaydet`}
                  disabled={!secrets[provider.id]?.trim()}
                  loading={busy === `save:${provider.id}`}
                  onClick={async () => {
                    const value = secrets[provider.id] ?? "";
                    setBusy(`save:${provider.id}`);
                    setSecrets((current) => ({ ...current, [provider.id]: "" }));
                    await perform("kontrol.anahtar_kaydet", { saglayici: provider.id, deger: value }, `${provider.ad} anahtarı kaydedildi.`);
                  }}
                  variant="secondary"
                >Kaydet</Button>
                {provider.kurulu && <Button aria-label={`${provider.ad} anahtarını sil`} onClick={() => void perform("kontrol.anahtar_sil", { saglayici: provider.id }, `${provider.ad} anahtarı silindi.`)} variant="ghost">Sil</Button>}
              </div>
            ))}
          </div>
        </section>

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

        <section className="control-panel__section">
          <div className="control-panel__section-heading"><div><span>Araç bağlantıları</span><h3>MCP sunucuları</h3></div><i data-online={state.mcp.length > 0}>{state.mcp.length} bağlı</i></div>
          {state.mcp.length ? <ul>{state.mcp.map((server) => <li key={server.ad}><strong>{server.ad}</strong><code>{server.komut}</code></li>)}</ul> : <p>Henüz MCP sunucusu eklenmedi.</p>}
        </section>
      </div>
    </main>
  );
}
