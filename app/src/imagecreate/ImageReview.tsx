import { useRef, useState } from "react";
import type { UretilenGorsel } from "./akisCalistir";
interface Props { image: UretilenGorsel; images: readonly UretilenGorsel[]; scope: string; comparison: string; onCompare: (path: string) => void; drafts?: Map<string, string> }
export function ImageReview(props: Props) {
  const drafts = useRef(new Map<string, string>());
  return <Review key={JSON.stringify([props.scope, props.image.yol])} {...props} drafts={props.drafts ?? drafts.current} />;
}
function Review({ image, images, scope, comparison, onCompare, drafts }: Props & { drafts: Map<string, string> }) {
  const key = JSON.stringify(["fusion.image-note.v1", scope, image.yol]);
  const [state, setState] = useState(() => {
    const recover = (value: { text: string; error: string; blocked: boolean; saved: boolean }) => drafts.has(key) ? { ...value, text: drafts.get(key)!, saved: false, error: value.error || "Not kaydedilemedi; açık çalışma alanındaki taslak korundu." } : value;
    try {
      const raw = localStorage.getItem(key);
      if (raw === null) return recover({ text: "", error: "", blocked: false, saved: false });
      const value = JSON.parse(raw);
      if (value?.schemaVersion !== 1 || typeof value.text !== "string" || value.text.length > 4000) throw new Error();
      return recover({ text: value.text as string, error: "", blocked: false, saved: true });
    } catch { return recover({ text: "", error: "Önceki not okunamadı; mevcut kayıt korunuyor.", blocked: true, saved: false }); }
  });
  return <section className="image-review" aria-label="Görsel inceleme">
    <label>Karşılaştırılacak görsel
      <select aria-label="Karşılaştırılacak görsel" value={comparison} onChange={event => onCompare(event.target.value)}>
        <option value="">Karşılaştırma kapalı</option>
        {images.filter(item => item.yol !== image.yol).map(item => <option key={item.yol} value={item.yol}>{item.istem || item.yol.split("/").pop()}</option>)}
      </select>
    </label>
    <label>Görsel notu
      <textarea aria-label="Görsel notu" maxLength={4000} rows={3} value={state.text} onChange={event => {
        const text = event.target.value.slice(0, 4000);
        drafts.set(key, text);
        if (state.blocked) { setState(previous => ({ ...previous, text })); return; }
        try {
          const raw = JSON.stringify({ schemaVersion: 1, text });
          localStorage.setItem(key, raw);
          if (localStorage.getItem(key) !== raw) throw new Error();
          drafts.delete(key);
          setState({ text, error: "", blocked: false, saved: true });
        } catch { setState({ text, error: "Not güvenle kaydedilemedi; metin açık kaldı.", blocked: false, saved: false }); }
      }} />
    </label>
    {state.error ? <><p role="alert">{state.error} Uygulamadan çıkmadan önce notu indir.</p><button type="button" onClick={() => {
      let url: string | undefined;
      try {
        url = URL.createObjectURL(new Blob([state.text], { type: "text/plain;charset=utf-8" }));
        const anchor = document.createElement("a"); anchor.href = url; anchor.download = "fusion-gorsel-notu.txt"; anchor.click();
      } catch { setState(previous => ({ ...previous, error: "Not indirilemedi; metni seçip kopyalayabilirsin." })); }
      finally {
        // Tarayıcının indirmeyi başlatabilmesi için URL hemen bırakılmaz.
        if (url) { const downloadUrl = url; setTimeout(() => URL.revokeObjectURL(downloadUrl), 1000); }
      }
    }}>Notu indir</button></> : state.saved ? <p role="status">Bu cihazda kaydedildi.</p> : null}
    <small>Not bu konuşma ve dosya için bu cihazda saklanır; diğer cihazlara aktarılmaz.</small>
    <small>Maske ile bölgesel düzenleme desteklenmiyor. Düzenleme isteği görselin tamamına uygulanır.</small>
  </section>;
}
