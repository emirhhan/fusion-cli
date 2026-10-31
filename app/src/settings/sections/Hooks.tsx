import { useEffect, useState } from "react";
import type { ProtocolClient } from "../../protocol/client";
import { errorMessage, operationResult } from "../../protocol/result";
import { ToggleRow } from "../PanelParts";

/**
 * Kancalar (P-009) — Claude Code `/hooks` gibi salt okunur liste.
 *
 * PreToolUse, PostToolUse, UserPromptSubmit, Stop, SessionStart… olaylarına bağlı kabuk
 * komutları. Tanımlar Fusion'ın `hooks.json`'ında, `~/.claude/settings.json`'da ve güvenilen
 * projenin `.claude/settings(.local).json` dosyalarında durur; düzenleme dosyada yapılır.
 * İki anahtar buradan değişir (`kanca.ayar`): tüm kancalar ve `~/.claude` kancaları.
 */

type HookFlag = "hooks_enabled" | "claude_hooks";

export interface HookRow {
  olay: string;
  eslestirici: string;
  komut: string;
  sure_sn: number | null;
  kaynak: string;
  dosya: string;
  /** Boş = etkin; doluysa neden çalışmadığı. */
  atlandi: string;
}

interface HooksPayload {
  ok?: boolean;
  metin?: string;
  kancalar?: HookRow[];
  kapali?: string | null;
  guvensiz_katmanlar?: string[];
  /** `disableAllHooks` taşıyan ama güvenilmediği için yok sayılan katmanlar. */
  yok_sayilan_kapatma?: string[];
  kullanici_dosyasi?: string;
  /** `runtime.hooks_enabled`. */
  etkin?: boolean;
  /** `runtime.claude_hooks`: `~/.claude/settings.json` kancaları çalışsın mı. */
  claude_kancalari?: boolean;
}

const KAYNAK_ETIKETI: Record<string, string> = {
  fusion: "Fusion (kullanıcı)",
  kullanici: "Claude (kullanıcı)",
  proje: "Proje",
  yerel: "Proje (yerel)",
};

export function HookList({ client }: { client: ProtocolClient }) {
  const [payload, setPayload] = useState<HooksPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let active = true;
    void (async () => {
      try {
        const result = (await client.request("kanca.listele", {})) as HooksPayload;
        if (!active) return;
        if (result?.ok === false) throw new Error(result.metin || "Kancalar okunamadı.");
        setPayload(result);
        setError(null);
      } catch (reason) {
        if (active) setError(`Kancalar okunamadı: ${errorMessage(reason)}`);
      }
    })();
    return () => { active = false; };
  }, [client]);

  const setFlag = async (anahtar: HookFlag, deger: boolean) => {
    setBusy(true);
    try {
      const result = (await client.request("kanca.ayar", { anahtar, deger })) as HooksPayload;
      const outcome = operationResult(result, "Kanca ayarı değiştirilemedi.");
      if (!outcome.ok) throw new Error(outcome.message);
      setPayload(result);
      setError(null);
    } catch (reason) {
      setError(`Kanca ayarı değiştirilemedi: ${errorMessage(reason)}`);
    } finally {
      setBusy(false);
    }
  };

  const rows = payload?.kancalar ?? [];
  const guvensiz = payload?.guvensiz_katmanlar ?? [];
  const yokSayilan = payload?.yok_sayilan_kapatma ?? [];
  return (
    <article className="settings__card settings__card--wide" id="settings-hooks">
      <div className="settings__card-head">
        <div>
          <h3>Kancalar</h3>
          <p className="settings__hint">
            Olaylara bağlı komutlar (Claude Code ile aynı biçim): <code>PreToolUse</code> çıkış 2 ile aracı engeller,{" "}
            <code>Stop</code> bitmemiş işi sürdürür, <code>SessionStart</code> bağlam ekler. Liste salt okunurdur.
          </p>
        </div>
      </div>
      {error && <p className="settings__hint" role="alert">{error}</p>}
      {payload && typeof payload.etkin === "boolean" && (
        <div className="permissions__blocks">
          <ToggleRow
            checked={payload.etkin}
            disabled={busy}
            title="Kancaları çalıştır"
            description="Kapalıyken hiçbir kanca çalışmaz (runtime.hooks_enabled). Açık oturumda bir sonraki görevde etkili olur."
            onChange={(deger) => void setFlag("hooks_enabled", deger)}
          />
          <ToggleRow
            checked={payload.claude_kancalari === true}
            disabled={busy}
            title="Claude Code kancalarını da çalıştır"
            description="~/.claude/settings.json içindeki kancalar (ECC gibi eklentiler) her araç çağrısında çalışır, araç girdi/çıktısını görür. Proje kancaları bundan bağımsızdır, proje güveni ister."
            onChange={(deger) => void setFlag("claude_hooks", deger)}
          />
        </div>
      )}
      {payload?.kapali && <p className="settings__hint" role="status"><strong>Kancalar kapalı:</strong> {payload.kapali}</p>}
      {yokSayilan.length > 0 && (
        <p className="settings__hint" role="status">
          Güvenilmeyen katmandaki <code>disableAllHooks</code> yok sayıldı ({yokSayilan.map((ad) => KAYNAK_ETIKETI[ad] ?? ad).join(", ")}): depo senin kancalarını kapatamaz.
        </p>
      )}
      {payload && rows.length === 0 && (
        <p className="settings__hint">
          Tanımlı kanca yok. <code>{payload.kullanici_dosyasi}</code> ya da <code>~/.claude/settings.json</code> içine{" "}
          <code>&quot;hooks&quot;</code> bloğu ekle (bkz. docs/KANCALAR.md).
        </p>
      )}
      {rows.length > 0 && (
        <table className="permissions__table">
          <thead>
            <tr><th scope="col">Olay</th><th scope="col">Eşleştirici</th><th scope="col">Komut</th><th scope="col">Kaynak</th></tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={`${row.dosya}:${row.olay}:${row.eslestirici}:${row.komut}`} data-skipped={row.atlandi ? "true" : "false"}>
                <td><code>{row.olay}</code></td>
                <td>{row.eslestirici ? <code>{row.eslestirici}</code> : "tümü"}</td>
                <td>
                  <code>{row.komut}</code>
                  {row.atlandi && <span className="permissions__decision" data-decision="ask"> atlandı: {row.atlandi}</span>}
                </td>
                <td title={row.dosya}>{KAYNAK_ETIKETI[row.kaynak] ?? row.kaynak}{row.sure_sn != null ? ` · ${row.sure_sn} sn` : ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {guvensiz.length > 0 && (
        <p className="settings__hint" role="status">
          Güvenilmediği için kancaları çalıştırılmayan katmanlar: {guvensiz.map((ad) => KAYNAK_ETIKETI[ad] ?? ad).join(", ")}. Dosyaları gözden geçirdiysen &quot;Bu projeye güven&quot; de.
        </p>
      )}
    </article>
  );
}
