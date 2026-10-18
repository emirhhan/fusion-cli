import { useCallback, useEffect, useState } from "react";
import { Button } from "../../ui/Button";
import type { ProtocolClient } from "../../protocol/client";

/**
 * Rol modelleri — varsayılan, öğretmen ve Fusion modu modellerini panelden seç.
 *
 * Seçim anında `config.yaml`'a kalıcı yazılır; elle dosya düzenlemek gerekmez.
 */

interface Option { model: string; etiket: string; grup: string; hazir: boolean; not: string; arac?: boolean }
interface WebSession { saglayici: string; hesap: string; etiket: string; dogrulandi: boolean }
interface Roles { agent: string; teacher: string; judge: string; candidates: string[]; codex_yedek?: boolean }

const ROLE_ROWS: { rol: "agent" | "teacher" | "judge"; baslik: string; aciklama: string; bos?: string }[] = [
  { rol: "agent", baslik: "Varsayılan model", aciklama: "Yeni sohbetlerde ve ajan modunda çalışan model." },
  { rol: "teacher", baslik: "Öğretmene sor modeli", aciklama: "Ajan takılınca danıştığı model; yalnız ChatGPT/Gemini SOHBET limitini harcar. Ulaşılamazsa ajan kendi başına sürer.", bos: "Otomatik (giriş yapılmış sohbet oturumları)" },
  { rol: "judge", baslik: "Fusion hakemi", aciklama: "Fusion modunda adayların cevaplarını karşılaştırıp kazananı seçer." },
];

function grouped(options: Option[]): [string, Option[]][] {
  const map = new Map<string, Option[]>();
  for (const option of options) map.set(option.grup, [...(map.get(option.grup) ?? []), option]);
  return [...map.entries()];
}

export function RoleModels({ client }: { client: ProtocolClient }) {
  const [options, setOptions] = useState<Option[]>([]);
  const [roles, setRoles] = useState<Roles | null>(null);
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [sessions, setSessions] = useState<WebSession[]>([]);
  const [verifying, setVerifying] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const payload = (await client.request("model.roller", {})) as { ok?: boolean; roller?: Roles; secenekler?: Option[]; oturumlar?: WebSession[] };
      if (payload.ok && payload.roller) { setRoles(payload.roller); setOptions(payload.secenekler ?? []); setSessions(payload.oturumlar ?? []); }
      else setNotice("Model listesi okunamadı.");
    } catch { setNotice("Model listesi okunamadı."); }
  }, [client]);
  useEffect(() => { void load(); }, [load]);

  /** Captcha/giriş: görünür Chrome'u aç, kapanınca oturumu kaydet ve gerçekten sına. */
  const verify = async (row: WebSession) => {
    const key = `${row.saglayici}/${row.hesap}`;
    setVerifying(key);
    const who = { saglayici: row.saglayici, hesap: row.hesap };
    try {
      const open = (await client.request("web.giris", who)) as { ok?: boolean; metin?: string; pid?: number };
      if (!open.ok || !open.pid) { setNotice(open.metin ?? "Doğrulama penceresi açılamadı."); return; }
      setNotice("Açılan Chrome'da captcha/girişi tamamla, sonra pencereyi kapat. Oturum otomatik sınanacak.");
      const deadline = Date.now() + 10 * 60_000;
      for (;;) {
        if (Date.now() >= deadline) { setNotice("Süre doldu. Tekrar dene."); return; }
        await new Promise((resolve) => setTimeout(resolve, 2000));
        const state = (await client.request("web.giris_durumu", { pid: open.pid })) as { acik?: boolean; ok?: boolean; metin?: string };
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

  const assign = async (rol: string, deger: unknown) => {
    setBusy(true);
    try {
      const result = (await client.request("model.rol_ata", { rol, deger })) as { ok?: boolean; metin?: string; roller?: Roles };
      setNotice(String(result.metin ?? (result.ok ? "Kaydedildi." : "Kaydedilemedi.")));
      if (result.ok && result.roller) setRoles(result.roller);
    } catch { setNotice("Kaydedilemedi."); }
    setBusy(false);
  };

  if (!roles) return <p className="settings__hint">{notice || "Modeller yükleniyor…"}</p>;
  const renderOptions = (needsTools: boolean) => grouped(options.filter((row) => !needsTools || row.arac !== false)).map(([group, rows]) => (
    <optgroup key={group} label={group}>
      {rows.map((row) => <option key={row.model} value={row.model}>{row.etiket}{row.not ? ` — ${row.not}` : ""}</option>)}
    </optgroup>
  ));
  const toggleCandidate = (model: string) => {
    const next = roles.candidates.includes(model) ? roles.candidates.filter((item) => item !== model) : [...roles.candidates, model];
    if (next.length > 0) void assign("candidates", next);
  };

  return (
    <article className="settings__card" aria-label="Rol modelleri">
      <h3>Roller ve modeller</h3>
      <p className="settings__hint">Seçtiğin an kalıcı kaydedilir; yeniden başlatmak gerekmez.</p>
      {ROLE_ROWS.map((row) => (
        <label key={row.rol} className="settings__field">
          <span>{row.baslik}</span>
          <select disabled={busy} aria-label={row.baslik} value={roles[row.rol]} onChange={(event) => void assign(row.rol, event.target.value)}>
            {row.bos !== undefined && <option value="">{row.bos}</option>}
            {renderOptions(row.rol === "agent")}
          </select>
          <small className="settings__hint">{row.aciklama}</small>
        </label>
      ))}
      <fieldset className="settings__field">
        <legend>Fusion modu adayları</legend>
        <small className="settings__hint">Fusion modu aynı görevi seçili modellerin hepsine verir. En az biri seçili kalır.</small>
        {options.map((row) => (
          <label key={row.model} className="settings__check">
            <input type="checkbox" disabled={busy} checked={roles.candidates.includes(row.model)} onChange={() => toggleCandidate(row.model)} />
            <span>{row.etiket}{row.not ? ` — ${row.not}` : ""}</span>
          </label>
        ))}
      </fieldset>
      <fieldset className="settings__field">
        <legend>Sohbet oturumları</legend>
        <small className="settings__hint">Öğretmen bu oturumların SOHBET limitini kullanır. Captcha çıkarsa düğmeye bas, açılan Chrome'da doğrula.</small>
        {sessions.map((row) => (
          <div key={`${row.saglayici}/${row.hesap}`} className="settings__check">
            <span>{row.etiket} — {row.dogrulandi ? "doğrulandı" : "doğrulama gerekli"}</span>
            <Button variant="secondary" disabled={verifying !== null} onClick={() => void verify(row)}>{verifying === `${row.saglayici}/${row.hesap}` ? "Bekleniyor…" : "Captcha'yı doğrula"}</Button>
          </div>
        ))}
      </fieldset>
      <label className="settings__check">
        <input type="checkbox" disabled={busy} checked={roles.codex_yedek === true} onChange={(event) => void assign("codex_yedek", event.target.checked)} />
        <span>Sohbet oturumları yanıt vermezse öğretmen için Codex'i de dene (Codex kodlama limitini harcar)</span>
      </label>
      {notice && <p className="settings__hint" role="status">{notice}</p>}
    </article>
  );
}
