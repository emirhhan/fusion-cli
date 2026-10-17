import type { IconName } from "../ui/Icon";
import type { ScheduleKind } from "./types";

/** Hazır başlangıç görevleri: tıklanınca yeni görev formu bunlarla dolar. */
export interface ScheduleTemplate {
  id: string;
  baslik: string;
  aciklama: string;
  /** Formda önceden seçilen istem. */
  gorev: string;
  simge: IconName;
  tur: ScheduleKind;
  saat: string;
  /** `haftalik` için gün indeksleri (0 = Pazartesi). */
  gunler?: number[];
}

const HAFTA_ICI = [0, 1, 2, 3, 4];

export const SCHEDULE_TEMPLATES: readonly ScheduleTemplate[] = [
  {
    id: "sabah-ozeti",
    baslik: "Sabah özeti",
    aciklama: "Projedeki son değişikliklerin, açık işlerin ve testlerin durumunun özeti.",
    gorev: "Projedeki son değişiklikleri, açık işleri ve test durumunu özetle; dikkat isteyenleri öne çıkar.",
    simge: "sun",
    tur: "haftalik",
    saat: "09:00",
    gunler: HAFTA_ICI,
  },
  {
    id: "saglik-kontrolu",
    baslik: "Sistem sağlık kontrolü",
    aciklama: "Altyapıyı ve servisleri hata, kesinti ve performans sorunları için denetle.",
    gorev: "Altyapıyı ve servisleri hata, kesinti ve performans sorunları için denetle; bulduklarını önem sırasıyla raporla.",
    simge: "pulse",
    tur: "gunluk",
    saat: "10:00",
  },
  {
    id: "pr-ozeti",
    baslik: "PR inceleme özeti",
    aciklama: "Açık PR'ların durumu ve nelerin dikkat istediğinin genel görünümü.",
    gorev: "Açık pull request'leri, inceleme durumlarını ve dikkat isteyenleri özetle.",
    simge: "branch",
    tur: "haftalik",
    saat: "17:00",
    gunler: HAFTA_ICI,
  },
  {
    id: "bagimlilik",
    baslik: "Bağımlılık güncelleme kontrolü",
    aciklama: "Eski paketleri, güvenlik yamalarını ve uyumsuz değişiklikleri tara.",
    gorev: "Eski paketleri, güvenlik yamalarını ve kırıcı değişiklikleri tara; güvenli güncellemeleri öner.",
    simge: "shield",
    tur: "haftalik",
    saat: "09:00",
    gunler: [0],
  },
  {
    id: "issue-siniflandirma",
    baslik: "Hata ve istek sınıflandırma",
    aciklama: "Gelen sorunları, hataları ve özellik isteklerini incele ve sınıflandır.",
    gorev: "Gelen sorunları, hataları ve özellik isteklerini incele; türüne ve önceliğine göre sınıflandır.",
    simge: "tasks",
    tur: "haftalik",
    saat: "18:00",
    gunler: HAFTA_ICI,
  },
  {
    id: "surum-notu",
    baslik: "Sürüm notu taslağı",
    aciklama: "Ana dala birleşen değişikliklerden kullanıcıya dönük sürüm notları hazırla.",
    gorev: "Ana dala birleşen değişikliklerden kullanıcıya dönük, sade bir sürüm notu taslağı hazırla.",
    simge: "scroll",
    tur: "haftalik",
    saat: "16:00",
    gunler: [4],
  },
  {
    id: "kararsiz-test",
    baslik: "Kararsız test takibi",
    aciklama: "Son koşularda bazen geçip bazen düşen testleri bul.",
    gorev: "Son test koşularında aralıklı geçen ve düşen kararsız testleri bul; olası nedenlerini yaz.",
    simge: "flask",
    tur: "haftalik",
    saat: "18:00",
    gunler: [0],
  },
];
