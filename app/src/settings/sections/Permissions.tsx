import { useCallback, useEffect, useRef, useState } from "react";
import type { ProtocolClient } from "../../protocol/client";
import { errorMessage, operationResult } from "../../protocol/result";
import { APPROVAL_MODES } from "../../screens/ApprovalModeMenu";
import { Button } from "../../ui/Button";
import { ToggleRow } from "../PanelParts";
import { HookList } from "./Hooks";
import "./Permissions.css";

/**
 * İzinler — Fusion'ın ne yapmasına izin verildiği.
 *
 * Eskiden üç satırlık bir tanım listesiydi ve hangisinin seçili olduğu ancak
 * metni okuyarak anlaşılıyordu. Mod artık SEÇİLİR; ne anlama geldiği seçeneğin
 * yanında yazar.
 *
 * Claude Code'un Customize › Permissions ekranı gibi kural tablosu da burada (P-003):
 * kalıp · karar · kaynak; ekle/sil. Kök-dışı okuma/yazma engelleri (P-002) ve proje
 * güveni (P-012) aynı bölümde.
 */

export const PERMISSION_MODES = APPROVAL_MODES.map((mod) => ({
  id: mod.id,
  etiket: mod.label,
  aciklama: mod.hint,
}));

export type RuleDecision = "allow" | "ask" | "deny";

export interface PermissionRuleRow {
  kalip: string;
  karar: RuleDecision;
  kaynak: string;
  dosya: string;
  /** Fusion bu satırı silebilir mi? Claude'un dosyaları ve güvenilmeyen yerel dosya salt okunur. */
  silinebilir?: boolean;
}

export interface TrustInfo {
  guvenildi: boolean;
  neden: string;
  dusurulen_bolumler: string[];
  yok_sayilan_dosyalar: string[];
  yuklenmeyen_araclar: number;
}

interface RulesPayload {
  ok?: boolean;
  metin?: string;
  kurallar?: PermissionRuleRow[];
  guvensiz_katmanlar?: string[];
  hedef?: string;
  kullanici_dosyasi?: string;
  kok_disi_okuma_engeli?: boolean;
  kok_disi_yazma_engeli?: boolean;
}

export const KARAR_ETIKETI: Record<RuleDecision, string> = {
  allow: "İzin ver",
  ask: "Her zaman sor",
  deny: "Yasakla",
};

/** Salt okunur satırın sil düğmesi ipucu: Claude'un dosyaları ve güvenilmeyen yerel dosya. */
const SALT_OKUNUR_IPUCU = "Bu dosya Fusion tarafından yazılmaz (Claude'un dosyası ya da güvenilmeyen yerel dosya); kuralı dosyadan elle kaldır.";

const KAYNAK_ETIKETI: Record<string, string> = {
  fusion: "Fusion (kullanıcı)",
  kullanici: "Claude (kullanıcı)",
  proje: "Proje",
  yerel: "Proje (yerel)",
};

function kaynakEtiketi(kaynak: string): string {
  const [ad, ...kalan] = kaynak.split(" ");
  const etiket = KAYNAK_ETIKETI[ad] ?? kaynak;
  return kalan.length ? `${etiket} ${kalan.join(" ")}` : etiket;
}

export function Permissions({
  client,
  guven,
  mod,
  pending = false,
  kok,
  kokleSinirli,
  onChangeRoot,
  onSelectMode,
  onTrustChange,
}: {
  /** Kural tablosu ve engeller için çekirdek bağlantısı; verilmezse yalnız mod ve klasör. */
  client?: ProtocolClient;
  guven?: TrustInfo | null;
  mod: string;
  pending?: boolean;
  kok: string;
  kokleSinirli: boolean;
  onChangeRoot?: () => void;
  onSelectMode?: (command: string) => void;
  /** Güven verildi/kaldırıldı: üst bileşen durumu yeniden okur. */
  onTrustChange?: () => void;
}) {
  // "İzinleri atla" hiçbir şey sormaz; tek tıkla açılmasın, önce açık onay istenir (U2-51).
  const [confirmBypass, setConfirmBypass] = useState(false);
  const [rules, setRules] = useState<RulesPayload | null>(null);
  const [rulesError, setRulesError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [kalip, setKalip] = useState("");
  const [karar, setKarar] = useState<RuleDecision>("allow");
  const [kapsam, setKapsam] = useState<"proje" | "kullanici">("proje");
  const [confirmUntrust, setConfirmUntrust] = useState(false);
  const owner = useRef(0);

  const loadRules = useCallback(async () => {
    if (!client) return;
    const generation = owner.current;
    try {
      const payload = (await client.request("izin.kurallar", {})) as RulesPayload;
      if (generation !== owner.current) return;
      if (payload?.ok === false) throw new Error(payload.metin || "İzin kuralları okunamadı.");
      setRules(payload);
      setRulesError(null);
    } catch (reason) {
      if (generation === owner.current) setRulesError(`İzin kuralları okunamadı: ${errorMessage(reason)}`);
    }
  }, [client]);

  useEffect(() => {
    const generation = ++owner.current;
    setRules(null); setRulesError(null);
    void loadRules();
    return () => { owner.current = generation + 1; };
  }, [loadRules]);

  const run = async (name: string, data: Record<string, unknown>, fallback: string) => {
    if (!client || busy) return false;
    setBusy(true); setRulesError(null);
    const generation = owner.current;
    try {
      const result = operationResult(await client.request(name, data), fallback);
      if (generation !== owner.current) return false;
      if (!result.ok) { setRulesError(result.message); return false; }
      await loadRules();
      return true;
    } catch (reason) {
      if (generation === owner.current) setRulesError(errorMessage(reason));
      return false;
    } finally {
      if (generation === owner.current) setBusy(false);
    }
  };

  const addRule = async () => {
    const metin = kalip.trim();
    if (!metin) return;
    if (await run("izin.ekle", { kalip: metin, karar, kapsam }, "Kural eklenemedi.")) setKalip("");
  };
  // Satırın DOSYASI da gider: aynı kural birden çok katmanda varsa tıklanan satır silinir.
  const removeRule = (row: PermissionRuleRow) => void run("izin.sil", { kalip: row.kalip, karar: row.karar, dosya: row.dosya }, "Kural silinemedi.");
  const setBlock = (anahtar: string, deger: boolean) => void run("izin.engel", { anahtar, deger }, "Engel değiştirilemedi.");
  const changeTrust = async (name: "proje.guven_ver" | "proje.guven_kaldir") => {
    setConfirmUntrust(false);
    if (await run(name, {}, "Güven değiştirilemedi.")) onTrustChange?.();
  };

  const kurallar = rules?.kurallar ?? [];
  const guvensiz = rules?.guvensiz_katmanlar ?? [];
  const dusurulen = guven ? [
    ...guven.dusurulen_bolumler,
    ...guven.yok_sayilan_dosyalar,
    ...(guven.yuklenmeyen_araclar > 0 ? [`${guven.yuklenmeyen_araclar} üretilmiş araç`] : []),
  ] : [];

  return (
    <>
      <article className="settings__card">
        <h3>Çalışma modu</h3>
        <div className="settings__choices" role="group">
          {PERMISSION_MODES.map((secenek) => (
            <button
              aria-pressed={secenek.id === mod}
              className="settings__choice"
              data-active={secenek.id === mod}
              disabled={!onSelectMode || pending}
              key={secenek.id}
              onClick={() => {
                if (secenek.id === "bypass" && mod !== "bypass") { setConfirmBypass(true); return; }
                setConfirmBypass(false);
                onSelectMode?.(`/${secenek.id}`);
              }}
              type="button"
            >
              <strong>{secenek.etiket}</strong>
              <small>{secenek.aciklama}</small>
            </button>
          ))}
        </div>
        {confirmBypass && (
          <div className="settings__warning" role="alert">
            <p>
              <strong>İzinleri atla</strong> modunda Fusion dosya yazma ve komut çalıştırma dahil hiçbir
              işlem için sormaz. Yalnız güvendiğin bir projede aç. Yasak (deny) kuralları bu modda da geçerlidir.
            </p>
            <div className="settings__actions">
              <Button disabled={pending} onClick={() => { setConfirmBypass(false); onSelectMode?.("/bypass"); }} variant="secondary">
                Evet, izinleri atla
              </Button>
              <Button onClick={() => setConfirmBypass(false)} variant="secondary">Vazgeç</Button>
            </div>
          </div>
        )}
        <p className="settings__hint">
          Sohbet ekranında Shift+Tab ile de değiştirebilirsin.
        </p>
      </article>

      <article className="settings__card">
        <h3>Proje klasörü</h3>
        <p className="settings__stat">{kok || "—"}</p>
        <p className="settings__hint">
          {kokleSinirli
            ? "Fusion yalnız bu klasörün içinde çalışır."
            : "Fusion bu klasörün dışına da onayınla çıkabilir."}
        </p>
        {onChangeRoot && (
          <div className="settings__actions">
            <Button onClick={onChangeRoot} variant="secondary">
              Klasörü değiştir
            </Button>
          </div>
        )}
        {client && rules && (
          <div className="permissions__blocks">
            <ToggleRow
              checked={rules.kok_disi_okuma_engeli === true}
              disabled={busy}
              title="Klasör dışını okumayı kapat"
              description="Açıkken dosya araçları proje klasörü (+ eklenen dizinler) dışını okuyamaz; sorulmaz, modele dizinin --add-dir ile açılabileceği söylenir."
              onChange={(deger) => setBlock("block_reads_outside_root", deger)}
            />
            <ToggleRow
              checked={rules.kok_disi_yazma_engeli === true}
              disabled={busy}
              title="Klasör dışına yazmayı kapat"
              description="Açıkken proje klasörü dışına yazma onay bile sorulmadan engellenir. Kapalıyken Otomatik kip dışarıya yazmayı sorar."
              onChange={(deger) => setBlock("block_writes_outside_root", deger)}
            />
          </div>
        )}
        {guven && (
          <div className="permissions__trust" data-trusted={guven.guvenildi}>
            <p className="settings__hint">
              <strong>{guven.guvenildi ? "Projeye güveniliyor." : "Projeye güvenilmiyor"}</strong>
              {guven.guvenildi
                ? " Projenin config.yaml, .claude ayarları ve üretilmiş araçları etkin."
                : ` (${guven.neden}).`}
              {!guven.guvenildi && dusurulen.length > 0 && (
                <> Devre dışı: {dusurulen.join(", ")}.</>
              )}
            </p>
            {client && (
              <div className="settings__actions">
                {guven.guvenildi ? (
                  confirmUntrust ? (
                    <>
                      <Button disabled={busy} onClick={() => void changeTrust("proje.guven_kaldir")} variant="danger">Evet, güveni kaldır</Button>
                      <Button onClick={() => setConfirmUntrust(false)} variant="secondary">Vazgeç</Button>
                    </>
                  ) : (
                    <Button disabled={busy} onClick={() => setConfirmUntrust(true)} variant="secondary">Güveni kaldır</Button>
                  )
                ) : (
                  <Button disabled={busy} onClick={() => void changeTrust("proje.guven_ver")} variant="primary">Bu projeye güven</Button>
                )}
              </div>
            )}
          </div>
        )}
      </article>

      {client && (
        <article className="settings__card settings__card--wide" id="settings-permission-rules">
          <div className="settings__card-head">
            <div>
              <h3>İzin kuralları</h3>
              <p className="settings__hint">
                Claude Code ile aynı biçim: <code>Bash(npm test *)</code>, <code>Edit(/src/**)</code>,{" "}
                <code>Read(~/.ssh/**)</code>, <code>WebFetch(domain:example.com)</code>, <code>mcp__sunucu__araç</code>.
                Yasak her modda geçerlidir; &quot;her zaman sor&quot; Otomatik kipte de sorar.
              </p>
            </div>
          </div>
          {rulesError && <p className="settings__hint" role="alert">{rulesError}</p>}
          {rules && kurallar.length === 0 && <p className="settings__hint">Henüz kural yok. Onay kartında &quot;bir daha sorma&quot; dediğinde ya da aşağıdan eklediğinde burada görünür.</p>}
          {kurallar.length > 0 && (
            <table className="permissions__table">
              <thead>
                <tr><th scope="col">Kalıp</th><th scope="col">Karar</th><th scope="col">Kaynak</th><th aria-label="İşlem" scope="col" /></tr>
              </thead>
              <tbody>
                {kurallar.map((row) => (
                  <tr key={`${row.dosya}:${row.karar}:${row.kalip}`} data-decision={row.karar}>
                    <td><code>{row.kalip}</code></td>
                    <td><span className="permissions__decision" data-decision={row.karar}>{KARAR_ETIKETI[row.karar] ?? row.karar}</span></td>
                    <td title={row.dosya}>{kaynakEtiketi(row.kaynak)}</td>
                    <td>
                      <Button
                        aria-label={`${row.kalip} kuralını sil`}
                        disabled={busy || row.silinebilir === false}
                        icon="close"
                        iconOnly
                        onClick={() => removeRule(row)}
                        title={row.silinebilir === false ? SALT_OKUNUR_IPUCU : undefined}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {guvensiz.length > 0 && (
            <p className="settings__hint" role="status">
              Güvenilmediği için <strong>izin ver</strong> kuralları yok sayılan katmanlar: {guvensiz.join(", ")} (yasakla/her zaman sor kuralları geçerli). Dosyaları gözden geçirdiysen &quot;Bu projeye güven&quot; de.
            </p>
          )}
          <form className="permissions__add" onSubmit={(event) => { event.preventDefault(); void addRule(); }}>
            <select aria-label="Karar" disabled={busy} onChange={(event) => setKarar(event.target.value as RuleDecision)} value={karar}>
              <option value="allow">İzin ver</option>
              <option value="ask">Her zaman sor</option>
              <option value="deny">Yasakla</option>
            </select>
            <input
              aria-label="Kalıp"
              disabled={busy}
              onChange={(event) => setKalip(event.target.value)}
              placeholder="Bash(npm test *)"
              spellCheck={false}
              value={kalip}
            />
            <select aria-label="Kapsam" disabled={busy} onChange={(event) => setKapsam(event.target.value as "proje" | "kullanici")} value={kapsam}>
              <option value="proje">Bu proje</option>
              <option value="kullanici">Tüm projeler</option>
            </select>
            <Button disabled={busy || !kalip.trim()} type="submit" variant="primary">Ekle</Button>
          </form>
          {rules?.hedef && (
            <p className="settings__hint">
              &quot;Bu proje&quot; → <code>{rules.hedef}</code> · &quot;Tüm projeler&quot; → <code>{rules.kullanici_dosyasi}</code>
            </p>
          )}
        </article>
      )}
      {client && <HookList client={client} key={guven ? String(guven.guvenildi) : "?"} />}
    </>
  );
}
