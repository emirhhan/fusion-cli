import { useEffect, useRef, useState } from "react";
import type { ProtocolClient } from "../protocol/client";
import { errorMessage, operationResult } from "../protocol/result";
import { Button } from "../ui/Button";
import "./TrustProject.css";

/**
 * Güvenilmeyen proje şeridi (P-012) — Claude Code'un "Do you trust the files in this
 * folder?" kartının Fusion karşılığı. Composer'ın üstünde, proje seçicinin kolonunda durur.
 *
 * Yalnız projenin GERÇEKTEN düşürülen bir ayarı varsa görünür: config.yaml'daki MCP
 * sunucuları / doğrulama komutları, `.claude/settings*.json` izin listeleri ve kanca (hook)
 * komutları ya da `.fusion/tools` araçları. Kanca varsa güvenin kabuk komutu çalıştıracağı
 * ayrıca söylenir (P-009): kullanıcı neye onay verdiğini bilmeli. Hiçbir şey düşürülmemişse soru anlamsızdır ve şerit çizilmez.
 * Kullanıcı "Şimdilik kapat" dediğinde aynı kök için bu pencere ömrünce bir daha çıkmaz.
 */

export interface TrustState {
  guvenildi: boolean;
  neden: string;
  dusurulen_bolumler: string[];
  yok_sayilan_dosyalar: string[];
  yuklenmeyen_araclar: number;
  /** Güvenilince kanca komutları çalışacak proje dosyaları. */
  kanca_dosyalari?: string[];
}

export function trustMatters(state: TrustState | null): boolean {
  if (!state || state.guvenildi) return false;
  // Claude gibi kullanıcı ayarındakiler dahil kancalar klasör güvenini bekler (#108).
  const kancalar = (state.kanca_dosyalari?.length ?? 0) > 0;
  return kancalar || state.dusurulen_bolumler.length > 0 || state.yok_sayilan_dosyalar.length > 0 || state.yuklenmeyen_araclar > 0;
}

export function dusurulenListesi(state: TrustState): string[] {
  const parcalar = [...state.dusurulen_bolumler, ...state.yok_sayilan_dosyalar];
  if (state.yuklenmeyen_araclar > 0) parcalar.push(`${state.yuklenmeyen_araclar} üretilmiş araç (.fusion/tools)`);
  return parcalar;
}

interface TrustProjectProps {
  client: ProtocolClient | undefined;
  kok: string;
  /** Tur sürüyorsa güven değiştirilemez (çekirdek reddeder); düğme kapalı kalır. */
  running?: boolean;
  /** Güven verildikten sonra üst bileşen durumunu yeniler. */
  onTrusted?: () => void;
}

/** Bu pencere ömrünce kapatılan kökler; yeniden açılışta soru yeniden sorulur. */
const kapatilan = new Set<string>();

export function TrustProject({ client, kok, running = false, onTrusted }: TrustProjectProps) {
  const [state, setState] = useState<TrustState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [dismissed, setDismissed] = useState(() => kapatilan.has(kok));
  const owner = useRef(0);

  useEffect(() => {
    const generation = ++owner.current;
    setState(null); setError(null); setDismissed(kapatilan.has(kok));
    if (!client) return;
    client.request("proje.guven_durum", {}).then((payload) => {
      if (generation !== owner.current) return;
      const data = payload as Partial<TrustState> & { ok?: boolean };
      if (data?.ok === false || typeof data?.guvenildi !== "boolean") return;
      setState({
        guvenildi: data.guvenildi,
        neden: data.neden ?? "",
        dusurulen_bolumler: Array.isArray(data.dusurulen_bolumler) ? data.dusurulen_bolumler : [],
        yok_sayilan_dosyalar: Array.isArray(data.yok_sayilan_dosyalar) ? data.yok_sayilan_dosyalar : [],
        yuklenmeyen_araclar: typeof data.yuklenmeyen_araclar === "number" ? data.yuklenmeyen_araclar : 0,
        kanca_dosyalari: Array.isArray(data.kanca_dosyalari) ? data.kanca_dosyalari : [],
      });
    }).catch(() => { /* güven durumu okunamazsa şerit çizilmez; sohbet çalışır */ });
    return () => { owner.current = generation + 1; };
  }, [client, kok]);

  if (dismissed || !trustMatters(state) || !state) return null;

  const trust = async () => {
    if (!client || busy) return;
    setBusy(true); setError(null);
    const generation = owner.current;
    try {
      const result = operationResult(await client.request("proje.guven_ver", {}), "Güven verilemedi.");
      if (generation !== owner.current) return;
      if (!result.ok) { setError(result.message); return; }
      setState((current) => (current ? { ...current, guvenildi: true } : current));
      onTrusted?.();
    } catch (reason) {
      if (generation === owner.current) setError(errorMessage(reason));
    } finally {
      if (generation === owner.current) setBusy(false);
    }
  };
  const dismiss = () => { kapatilan.add(kok); setDismissed(true); };

  return (
    <div className="trust-project-kolon">
      <aside aria-label="Proje güveni" className="trust-project" role="note">
        <p className="trust-project__metin">
          <strong>Bu klasördeki dosyalara güveniyor musun?</strong>{" "}
          {dusurulenListesi(state).length > 0
            ? <>Proje kendi ayarlarını taşıyor ({dusurulenListesi(state).join(", ")}); {state.neden}. Güvenmediğin sürece bunlar devre dışı kalır.</>
            : <>Güvenene dek kancalar (hook) çalışmaz.</>}
        </p>
        {(state.kanca_dosyalari?.length ?? 0) > 0 && (
          <p className="trust-project__metin">
            <strong>Dikkat:</strong> {state.kanca_dosyalari?.join(", ")} kanca (hook) komutları içeriyor; güvenirsen bunlar her araç çağrısında senin yetkinle çalışır.
          </p>
        )}
        {error && <p className="trust-project__hata" role="alert">{error}</p>}
        <div className="trust-project__eylemler">
          <Button disabled={busy || running} onClick={() => void trust()} variant="primary">Evet, güven</Button>
          <Button onClick={dismiss} variant="ghost">Şimdilik kapat</Button>
          {running && <small>Önce çalışan görevi durdur.</small>}
        </div>
      </aside>
    </div>
  );
}
