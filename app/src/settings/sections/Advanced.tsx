import { Button } from "../../ui/Button";

/**
 * Gelişmiş — çoğu kullanıcının hiç açmayacağı ama gerektiğinde bulunması
 * gereken şeyler.
 *
 * "Gateway" adı kaldırıldı. Kullanıcının ölçülmüş sorusu aynen şuydu:
 * "gateway nedir ben bile bilmiyorum". Özellik gerçek ve yararlı — Cursor,
 * Cline gibi araçlar Fusion'ın model yönlendirmesini bu uçtan kullanabiliyor —
 * ama adı ne olduğunu değil ne YAPTIĞINI söylemeli.
 */

export function Advanced({
  adres,
  calisiyor,
  mesgul,
  onToggle,
}: {
  adres: string;
  calisiyor: boolean;
  mesgul: boolean;
  onToggle: () => void;
}) {
  return (
    <article className="settings__card">
      <div className="settings__card-head">
        <h3>Yerel API ucu</h3>
        <i data-online={calisiyor}>{calisiyor ? "Çalışıyor" : "Kapalı"}</i>
      </div>
      <p className="settings__hint">
        Cursor, Cline ve OpenAI uyumlu diğer araçlar bu adresten Fusion'ın model
        yönlendirmesini kullanabilir. Bilgisayarının dışına açılmaz.
      </p>
      <code className="settings__endpoint">{adres || "—"}</code>
      <div className="settings__actions">
        <Button
          loading={mesgul}
          onClick={onToggle}
          variant={calisiyor ? "danger" : "primary"}
        >
          {calisiyor ? "Durdur" : "Başlat"}
        </Button>
      </div>
    </article>
  );
}
