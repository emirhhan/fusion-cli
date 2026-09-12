import { useState } from "react";
import { Button } from "../ui/Button";
import { PageHeader } from "../ui/PageHeader";
import "./help.css";

/**
 * Yardım ekranı.
 *
 * Eskiden "Yardım" menüsü Dersler ekranını açıyordu: iki ayrı menü öğesi aynı
 * yere gidiyordu ve kullanıcı aradığını bulamıyordu. Dersler kaldırıldı; burası
 * ARANAN ŞEYİ veren yer oldu — kısayollar, sık sorulanlar ve bir şey ters
 * gittiğinde nereye bakılacağı.
 *
 * İçerik ÜRÜNÜN GERÇEĞİNİ anlatır: uydurma bir özellik ya da var olmayan bir
 * menü tarif edilmez.
 */

interface Kisayol {
  tus: string;
  ne: string;
}

const KISAYOLLAR: Kisayol[] = [
  { tus: "Enter", ne: "Görevi gönder" },
  { tus: "Shift + Enter", ne: "Alt satıra geç" },
  { tus: "Shift + Tab", ne: "İzin modunu değiştir (Otomatik / Yalnız plan / Güvenli)" },
  { tus: "/", ne: "Komut paletini aç" },
  { tus: "Esc", ne: "Açık menüyü ya da seçiciyi kapat" },
];

interface Soru {
  baslik: string;
  cevap: string;
}

const SORULAR: Soru[] = [
  {
    baslik: "Parolamı unuttum, ne olacak?",
    cevap:
      "Hesaplar bu bilgisayarda tutulur; sıfırlama e-postası gönderebileceğimiz bir sunucu yok. " +
      "Giriş ekranındaki 'Şifremi Unuttum' yolundan, hesabı açarken verilen kurtarma kodunu " +
      "kullanabilirsin. Kod yoksa o hesaba girilemez.",
  },
  {
    baslik: "Fusion neden bir şeyi yapamadığını söylüyor?",
    cevap:
      "Bazı modeller dosya değiştiremez. Bir sağlayıcının araç desteği doğrulanmamışsa Fusion " +
      "onu okuma ve planlamayla sınırlar; yapılmamış bir işi yapılmış göstermez. Hangi modelin " +
      "ne yapabildiğini Ayarlar'daki sağlayıcı listesinde görebilirsin.",
  },
  {
    baslik: "İzin modları ne işe yarıyor?",
    cevap:
      "Otomatik: Fusion kendi ilerler, yıkıcı işlemde sorar. Yalnız plan: hiçbir şeyi " +
      "değiştirmez. Güvenli mod: her değiştirici işlem için ayrı ayrı onay ister. " +
      "Görev kutusunun altından ya da Shift+Tab ile değiştirilir.",
  },
  {
    baslik: "Sağlayıcıya giriş yaparken tarayıcı açılıyor, normal mi?",
    cevap:
      "Evet — giriş sağlayıcının kendi sayfasında yapılır ve parolan Fusion'a hiç gelmez. " +
      "Giriş dışındaki işlerde tarayıcı penceresi görünmez.",
  },
  {
    baslik: "Bir hesabı silersem ne gider?",
    cevap:
      "O hesabın ayarları: sağlayıcı oturumları, MCP bağlantıları ve model tercihleri. " +
      "Silme geri alınamaz, bu yüzden onay için kullanıcı adını elle yazman istenir.",
  },
];

export function HelpScreen({
  onClose,
  onOpenSettings,
  surum,
}: {
  onClose: () => void;
  onOpenSettings?: () => void;
  /** Çalışan sürüm; hata bildirirken işe yarar. */
  surum?: string;
}) {
  const [acik, setAcik] = useState<string | null>(null);

  return (
    <main className="help">
      <PageHeader
        actions={<Button onClick={onClose} variant="secondary">Kapat</Button>}
        description="Kısayollar, sık sorulanlar ve bir şey ters gittiğinde ne yapılacağı."
        eyebrow="Yardım"
        title="Yardım"
      />

      <section className="help__card">
        <h3>Kısayollar</h3>
        <dl className="help__shortcuts">
          {KISAYOLLAR.map((kisayol) => (
            <div key={kisayol.tus}>
              <dt><kbd>{kisayol.tus}</kbd></dt>
              <dd>{kisayol.ne}</dd>
            </div>
          ))}
        </dl>
      </section>

      <section className="help__card">
        <h3>Sık sorulanlar</h3>
        {SORULAR.map((soru) => (
          <details
            key={soru.baslik}
            onToggle={(event) =>
              setAcik(event.currentTarget.open ? soru.baslik : null)
            }
            open={acik === soru.baslik}
          >
            <summary>{soru.baslik}</summary>
            <p>{soru.cevap}</p>
          </details>
        ))}
      </section>

      <section className="help__card">
        <h3>Bir şey ters gittiğinde</h3>
        <p>
          Önce Ayarlar'daki sağlayıcı ve bağlantı durumlarına bak: çoğu sorun düşmüş bir
          oturumdan ya da bağlanmamış bir MCP sunucusundan gelir.
        </p>
        {onOpenSettings && (
          <Button onClick={onOpenSettings} variant="secondary">Ayarlar'ı aç</Button>
        )}
        {surum && <p className="help__version">Sürüm {surum}</p>}
      </section>
    </main>
  );
}
