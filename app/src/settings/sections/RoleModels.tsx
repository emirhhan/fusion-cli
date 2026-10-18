import { useCallback, useEffect, useState } from "react";
import { ProviderLogo, type ProviderId } from "../../brand/ProviderLogo";
import { Button } from "../../ui/Button";
import type { ProtocolClient } from "../../protocol/client";
import "./RoleModels.css";

/**
 * Roller ve modeller — kare kartlar.
 *
 * Her rol bir kart: üstte rolün adı, altta seçili model. Karta dokununca modellerin
 * kart ızgarası açılır; seçim anında `config.yaml`'a kalıcı yazılır.
 */

interface Option { model: string; etiket: string; grup: string; hazir: boolean; not: string; arac?: boolean }
interface WebSession { saglayici: string; hesap: string; etiket: string; dogrulandi: boolean }
interface Roles { agent: string; teacher: string; judge: string; candidates: string[]; codex_yedek?: boolean; web_yedek?: boolean }

type RoleId = "agent" | "teacher" | "judge" | "candidates";

const ROLES: { id: RoleId; baslik: string; aciklama: string; ikon: string }[] = [
  { id: "agent", baslik: "Varsayılan model", aciklama: "Yeni sohbet ve ajan modunda çalışır.", ikon: "◆" },
  { id: "teacher", baslik: "Öğretmene sor", aciklama: "Ajan takılınca danışır; yalnız sohbet limitini harcar.", ikon: "✦" },
  { id: "judge", baslik: "Fusion hakemi", aciklama: "Adayların cevaplarını karşılaştırıp kazananı seçer.", ikon: "⚖" },
  { id: "candidates", baslik: "Fusion adayları", aciklama: "Fusion modunda aynı göreve birlikte çalışan modeller.", ikon: "❖" },
];

const AUTO = "";

function providerOf(model: string): ProviderId | null {
  const id = model.split("/")[0];
  return id === "chatgpt_web" || id === "gemini_web" || id === "claude_web" || id === "copilot_web" ? id : null;
}

function Mark({ model, size = 20 }: { model: string; size?: number }) {
  const web = providerOf(model);
  if (web) return <ProviderLogo id={web} size={size} />;
  if (model.startsWith("codex_cli/")) return <ProviderLogo id="chatgpt_web" size={size} />;
  return <span aria-hidden="true">{(model.split("/")[0] || "?").slice(0, 1).toUpperCase()}</span>;
}

export function RoleModels({ client }: { client: ProtocolClient }) {
  const [options, setOptions] = useState<Option[]>([]);
  const [roles, setRoles] = useState<Roles | null>(null);
  const [sessions, setSessions] = useState<WebSession[]>([]);
  const [open, setOpen] = useState<RoleId | null>(null);
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [verifying, setVerifying] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const payload = (await client.request("model.roller", {})) as { ok?: boolean; roller?: Roles; secenekler?: Option[]; oturumlar?: WebSession[] };
      if (payload.ok && payload.roller) { setRoles(payload.roller); setOptions(payload.secenekler ?? []); setSessions(payload.oturumlar ?? []); }
      else setNotice("Model listesi okunamadı.");
    } catch { setNotice("Model listesi okunamadı."); }
  }, [client]);
  useEffect(() => { void load(); }, [load]);

  const assign = async (rol: string, deger: unknown) => {
    setBusy(true);
    try {
      const result = (await client.request("model.rol_ata", { rol, deger })) as { ok?: boolean; metin?: string; roller?: Roles };
      setNotice(String(result.metin ?? (result.ok ? "Kaydedildi." : "Kaydedilemedi.")));
      if (result.ok && result.roller) setRoles(result.roller);
    } catch { setNotice("Kaydedilemedi."); }
    setBusy(false);
  };

  /** Captcha/giriş: görünür Chrome'u aç, kapanınca oturumu kaydet ve gerçekten sına. */
  const verify = async (row: WebSession) => {
    const key = `${row.saglayici}/${row.hesap}`;
    setVerifying(key);
    const who = { saglayici: row.saglayici, hesap: row.hesap };
    try {
      const opened = (await client.request("web.giris", who)) as { ok?: boolean; metin?: string; pid?: number };
      if (!opened.ok || !opened.pid) { setNotice(opened.metin ?? "Doğrulama penceresi açılamadı."); return; }
      setNotice("Açılan Chrome'da captcha/girişi tamamla, sonra pencereyi kapat. Oturum otomatik sınanacak.");
      const deadline = Date.now() + 10 * 60_000;
      for (;;) {
        if (Date.now() >= deadline) { setNotice("Süre doldu. Tekrar dene."); return; }
        await new Promise((resolve) => setTimeout(resolve, 2000));
        const state = (await client.request("web.giris_durumu", { pid: opened.pid })) as { acik?: boolean; ok?: boolean; metin?: string };
        if (state.ok === false) { setNotice(state.metin ?? "Giriş tamamlanamadı."); return; }
        if (!state.acik) break;
      }
      setNotice("Oturum kaydediliyor ve sınanıyor…");
      const saved = (await client.request("web.baglan", who)) as { ok?: boolean; metin?: string };
      if (!saved.ok) { setNotice(saved.metin ?? "Oturum kaydedilemedi."); return; }
      const test = (await client.request("web.dogrula", who)) as { ok?: boolean; metin?: string };
      setNotice(test.ok ? `${row.etiket}: doğrulandı.` : (test.metin ?? `${row.etiket}: doğrulanamadı.`));
    } catch { setNotice("Doğrulama tamamlanamadı."); }
    finally { setVerifying(null); void load(); }
  };

  if (!roles) return <p className="settings__hint">{notice || "Modeller yükleniyor…"}</p>;

  const labelOf = (model: string) => options.find((item) => item.model === model)?.etiket ?? model;
  const summary = (id: RoleId) => {
    if (id === "candidates") return roles.candidates.length === 1 ? labelOf(roles.candidates[0]) : `${roles.candidates.length} model`;
    const value = roles[id === "agent" ? "agent" : id === "teacher" ? "teacher" : "judge"];
    return value ? labelOf(value) : "Otomatik";
  };
  const markModel = (id: RoleId) => id === "candidates" ? roles.candidates[0] ?? "" : (roles[id] || "");
  const isSelected = (id: RoleId, model: string) => id === "candidates" ? roles.candidates.includes(model) : roles[id] === model;

  const pick = (id: RoleId, model: string) => {
    if (id === "candidates") {
      const next = roles.candidates.includes(model) ? roles.candidates.filter((item) => item !== model) : [...roles.candidates, model];
      if (next.length > 0) void assign("candidates", next);
      return;
    }
    void assign(id, model);
  };

  const pickable = (id: RoleId) => options.filter((row) => id !== "agent" || row.arac !== false);
  const active = ROLES.find((role) => role.id === open) ?? null;

  return (
    <section className="rm" aria-label="Roller ve modeller">
      <header className="rm__head">
        <h3>Roller ve modeller</h3>
        <p>Karta dokun, modeli seç. Seçim anında kalıcı kaydedilir; yeniden başlatmak gerekmez.</p>
      </header>

      <ul className="rm__roles">
        {ROLES.map((role) => (
          <li key={role.id}>
            <button
              aria-expanded={open === role.id}
              aria-label={role.baslik}
              className="rm__role"
              onClick={() => setOpen((current) => (current === role.id ? null : role.id))}
              type="button"
            >
              <span className="rm__role-top">
                <span className="rm__glyph" aria-hidden="true">{role.ikon}</span>
                <span className="rm__chev" aria-hidden="true">›</span>
              </span>
              <span className="rm__role-name">{role.baslik}</span>
              <span className="rm__role-value">
                {markModel(role.id) ? <span className="rm__mini"><Mark model={markModel(role.id)} size={14} /></span> : null}
                <span>{summary(role.id)}</span>
              </span>
            </button>
          </li>
        ))}
      </ul>

      {active && (
        <div className="rm__picker" role="region" aria-label={`${active.baslik} için model seç`}>
          <div className="rm__picker-head">
            <div><h4>{active.baslik}</h4><p>{active.aciklama}</p></div>
            <button aria-label="Kapat" className="rm__x" onClick={() => setOpen(null)} type="button">×</button>
          </div>
          <ul className="rm__models">
            {active.id === "teacher" && (
              <li>
                <button aria-pressed={roles.teacher === AUTO} className="rm__model" disabled={busy} onClick={() => void assign("teacher", AUTO)} type="button">
                  <span className="rm__mini rm__mini--lg" aria-hidden="true">✺</span>
                  <span className="rm__model-name">Otomatik</span>
                  <span className="rm__model-note">Giriş yapılmış sohbet oturumları</span>
                </button>
              </li>
            )}
            {pickable(active.id).map((row) => (
              <li key={row.model}>
                <button
                  aria-pressed={isSelected(active.id, row.model)}
                  className="rm__model"
                  disabled={busy}
                  onClick={() => pick(active.id, row.model)}
                  type="button"
                >
                  <span className="rm__mini rm__mini--lg"><Mark model={row.model} size={20} /></span>
                  <span className="rm__model-name">{row.etiket}</span>
                  <span className="rm__model-note" data-warn={!row.hazir}>{row.not || row.grup}</span>
                  {isSelected(active.id, row.model) && <span className="rm__check" aria-hidden="true">✓</span>}
                </button>
              </li>
            ))}
          </ul>
          {active.id === "candidates" && <p className="rm__tip">Birden fazla seçebilirsin; en az bir model seçili kalır.</p>}
        </div>
      )}

      <div className="rm__sub">
        <h4>Sohbet oturumları</h4>
        <p>Öğretmen bu oturumların SOHBET limitini kullanır. Captcha çıkarsa kartın düğmesine bas, açılan Chrome'da doğrula.</p>
        <ul className="rm__sessions">
          {sessions.map((row) => {
            const key = `${row.saglayici}/${row.hesap}`;
            return (
              <li className="rm__session" key={key}>
                <span className="rm__mini rm__mini--lg"><Mark model={`${row.saglayici}/`} size={20} /></span>
                <span className="rm__session-name">{row.etiket}</span>
                <span className="rm__session-state" data-ok={row.dogrulandi}><i aria-hidden="true" />{row.dogrulandi ? "doğrulandı" : "doğrulama gerekli"}</span>
                <Button variant="secondary" disabled={verifying !== null} onClick={() => void verify(row)}>
                  {verifying === key ? "Bekleniyor…" : "Captcha'yı doğrula"}
                </Button>
              </li>
            );
          })}
        </ul>
      </div>

      <label className="rm__switch">
        <input type="checkbox" role="switch" disabled={busy} checked={roles.web_yedek !== false} onChange={(event) => void assign("web_yedek", event.target.checked)} />
        <span className="rm__switch-ui" aria-hidden="true" />
        <span>
          <b>Otomatik yedek model</b>
          <small>Seçili model cevap veremezse (kapalı, bağlam taştı, sunucu hatası) giriş yapılmış ve araç ölçümünü geçmiş web oturumuna otomatik geç.</small>
        </span>
      </label>
      <label className="rm__switch">
        <input type="checkbox" role="switch" disabled={busy} checked={roles.codex_yedek === true} onChange={(event) => void assign("codex_yedek", event.target.checked)} />
        <span className="rm__switch-ui" aria-hidden="true" />
        <span>
          <b>Codex yedeği</b>
          <small>Sohbet oturumları yanıt vermezse öğretmen için Codex'i de dene. Codex kodlama limitini harcar.</small>
        </span>
      </label>

      {notice && <p className="rm__notice" role="status">{notice}</p>}
    </section>
  );
}
