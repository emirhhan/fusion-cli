import type { AkisDugumu, DugumDurumu, IsAkisiDurumu } from "./orkestrasyon";
import "./OrchestrationBoard.css";

/**
 * İş akışı panosu (P-062): koşunun evresi, ilerlemesi ve düğüm durumları.
 *
 * Düğümler evreye göre gruplanır; uzun listede yalnız ilk satırlar açık durur, gerisi
 * "tümü" ile açılır. Durum hem renk hem metinle verilir (renk körlüğü). Koşu
 * kimliği `/workflows iptal <kimlik>` için görünür.
 */

const DURUM: Record<DugumDurumu, string> = {
  bekliyor: "bekliyor",
  calisiyor: "çalışıyor",
  tamam: "tamam",
  basarisiz: "başarısız",
  iptal: "iptal",
  atlandi: "atlandı",
};

const KOSU_DURUMU: Record<string, string> = {
  calisiyor: "Çalışıyor",
  tamam: "Tamamlandı",
  yarim: "Yarım kaldı",
  iptal: "İptal edildi",
  hata: "Hata",
};

/** Açık gösterilen en fazla düğüm; fazlası katlanır. */
export const ACIK_DUGUM = 12;

function evreler(dugumler: AkisDugumu[]): [string, AkisDugumu[]][] {
  const gruplar = new Map<string, AkisDugumu[]>();
  for (const dugum of dugumler) gruplar.set(dugum.evre, [...(gruplar.get(dugum.evre) ?? []), dugum]);
  return [...gruplar.entries()];
}

function DugumSatiri({ dugum }: { dugum: AkisDugumu }) {
  return <li className="orch-node" data-durum={dugum.durum}>
    <span aria-hidden="true" className="orch-node__dot" />
    <span className="orch-node__label">{dugum.etiket || dugum.id}</span>
    <span className="orch-node__state">{DURUM[dugum.durum]}</span>
    {dugum.ozet && dugum.durum !== "tamam" && <span className="orch-node__note">{dugum.ozet}</span>}
  </li>;
}

function DugumListesi({ dugumler }: { dugumler: AkisDugumu[] }) {
  const acik = dugumler.slice(0, ACIK_DUGUM);
  const kalan = dugumler.slice(ACIK_DUGUM);
  return <>
    <ul className="orch-board__nodes">{acik.map((dugum) => <DugumSatiri dugum={dugum} key={dugum.id} />)}</ul>
    {kalan.length > 0 && <details className="orch-board__more">
      <summary>{kalan.length} adım daha</summary>
      <ul className="orch-board__nodes">{kalan.map((dugum) => <DugumSatiri dugum={dugum} key={dugum.id} />)}</ul>
    </details>}
  </>;
}

export function WorkflowBoard({ akis, running }: { akis: IsAkisiDurumu; running: boolean }) {
  const toplam = akis.dugumler.length;
  const biten = akis.dugumler.filter((dugum) => !["bekliyor", "calisiyor"].includes(dugum.durum)).length;
  const durum = akis.durum === "calisiyor" && !running ? "Yarım kaldı" : KOSU_DURUMU[akis.durum] ?? akis.durum;
  return <section aria-label={`İş akışı ${akis.ad}`} className="orch-board" data-durum={akis.durum}>
    <header className="orch-board__head">
      <p className="orch-board__eyebrow">İş akışı</p>
      <h3 className="orch-board__title">{akis.ad}</h3>
      <span className="orch-board__status">{durum}</span>
    </header>
    <p className="orch-board__meta">
      {akis.evre && <span>Evre: {akis.evre}</span>}
      <span>{biten}/{toplam} adım</span>
      <span>{akis.ajanSayisi}/{akis.ajanTavani} ajan</span>
      <span>{Math.round(akis.sureSn)} sn</span>
      <code title="/workflows iptal ile durdurulur">{akis.kimlik}</code>
    </p>
    <progress aria-label="İlerleme" className="orch-board__progress" max={Math.max(1, toplam)} value={biten} />
    {akis.mesaj && <p className="orch-board__message">{akis.mesaj}</p>}
    {evreler(akis.dugumler).map(([evre, dugumler]) => <div className="orch-board__phase" key={evre || "-"}>
      {evre && <p className="orch-board__phase-name">{evre}</p>}
      <DugumListesi dugumler={dugumler} />
    </div>)}
  </section>;
}
