import type { EkipPanosu, PanoGorevi } from "./orkestrasyon";
import "./OrchestrationBoard.css";

/**
 * Ekip panosu (P-061): paylaşımlı görev listesi üç sütunda (bekliyor / çalışıyor /
 * bitti), üyelerin anlık durumu ve posta kutusunun son mesajları. Kartlar (alt ajanlar)
 * aynı mesajda panonun altında akar.
 */

const UYE_DURUMU: Record<string, string> = {
  bekliyor: "bekliyor", sirada: "sırada", calisiyor: "çalışıyor", bosta: "boşta", bitti: "bitti",
};
const EKIP_DURUMU: Record<string, string> = { calisiyor: "Çalışıyor", bitti: "Tamamlandı", durdu: "Durdu" };
const SUTUNLAR: { baslik: string; durumlar: string[] }[] = [
  { baslik: "Bekliyor", durumlar: ["bekliyor"] },
  { baslik: "Çalışıyor", durumlar: ["calisiyor"] },
  { baslik: "Bitti", durumlar: ["tamam", "basarisiz"] },
];
/** Panoda gösterilen son mesaj sayısı. */
export const SON_MESAJ = 5;

function GorevKarti({ gorev }: { gorev: PanoGorevi }) {
  const ayrinti = [gorev.sahip, gorev.bagimli.length ? `bağımlı: ${gorev.bagimli.join(", ")}` : ""].filter(Boolean).join(" · ");
  return <li className="orch-task" data-durum={gorev.durum}>
    <span className="orch-task__title"><code>{gorev.id}</code> {gorev.baslik}</span>
    {ayrinti && <small>{ayrinti}</small>}
    {gorev.durum === "basarisiz" && <small className="orch-task__failed">başarısız{gorev.sonuc ? `: ${gorev.sonuc}` : ""}</small>}
  </li>;
}

export function TeamBoard({ pano, running }: { pano: EkipPanosu; running: boolean }) {
  const tamam = pano.gorevler.filter((gorev) => gorev.durum === "tamam").length;
  const durum = pano.durum === "calisiyor" && !running ? "Yarım kaldı" : EKIP_DURUMU[pano.durum] ?? pano.durum;
  const mesajlar = pano.mesajlar.slice(-SON_MESAJ);
  return <section aria-label={`Ekip ${pano.ad}`} className="orch-board" data-durum={pano.durum}>
    <header className="orch-board__head">
      <p className="orch-board__eyebrow">Ekip</p>
      <h3 className="orch-board__title">{pano.ad}</h3>
      <span className="orch-board__status">{durum}</span>
    </header>
    {pano.hedef && <p className="orch-board__goal">{pano.hedef}</p>}
    <ul aria-label="Üyeler" className="orch-board__members">
      {pano.uyeler.map((uye) => <li className="orch-member" data-durum={uye.durum} key={uye.ad}>
        <span aria-hidden="true" className="orch-node__dot" />
        <strong>{uye.ad}</strong>{uye.uzman && <small> {uye.uzman}</small>}
        <small> · {UYE_DURUMU[uye.durum] ?? uye.durum}{uye.uyanma ? ` · ${uye.uyanma} uyanma` : ""}</small>
      </li>)}
    </ul>
    <progress aria-label="Görev ilerlemesi" className="orch-board__progress" max={Math.max(1, pano.gorevler.length)} value={tamam} />
    <div className="orch-board__columns">
      {SUTUNLAR.map((sutun) => {
        const gorevler = pano.gorevler.filter((gorev) => sutun.durumlar.includes(gorev.durum));
        return <div className="orch-board__column" key={sutun.baslik}>
          <p className="orch-board__phase-name">{sutun.baslik} · {gorevler.length}</p>
          <ul className="orch-board__nodes">{gorevler.map((gorev) => <GorevKarti gorev={gorev} key={gorev.id} />)}</ul>
        </div>;
      })}
    </div>
    {mesajlar.length > 0 && <details className="orch-board__more">
      <summary>Posta kutusu · son {mesajlar.length} mesaj</summary>
      <ul className="orch-board__mail">
        {mesajlar.map((mesaj, index) => <li key={`${index}-${mesaj.kimden}`}><strong>{mesaj.kimden} → {mesaj.kime}</strong> {mesaj.metin}</li>)}
      </ul>
    </details>}
  </section>;
}
