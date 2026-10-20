import type { ReactNode } from "react";
import { Icon } from "../ui/Icon";
import "./MediaScreen.css";

export type MediaPage = "image-create" | "video-create";

interface MediaScreenProps {
  active: MediaPage;
  /** Görsel üretim ekranı; video sekmesinde çizilmez. */
  image: ReactNode;
  onSelect: (page: MediaPage) => void;
}

/** Görsel ve video üretimi: üstte tek satırda tür seçici, altında seçilen ekran.
 *
 * Seçici, görsel ekranının kendi üst satırının (Basit oluştur / İş akışı) soluna
 * oturur; ayrı bir şerit açılmaz. */
export function MediaScreen({ active, image, onSelect }: MediaScreenProps) {
  return (
    <div className="media-screen">
      <div aria-label="Üretim türü" className="media-screen__tabs" role="tablist">
        <button aria-selected={active === "image-create"} onClick={() => onSelect("image-create")} role="tab" type="button">
          <Icon name="image" size={15} /> Görsel
        </button>
        <button aria-selected={active === "video-create"} onClick={() => onSelect("video-create")} role="tab" type="button">
          <Icon name="video" size={15} /> Video
        </button>
      </div>
      {active === "image-create" ? image : (
        <section aria-label="Video oluştur" className="media-screen__soon">
          <span aria-hidden="true" className="media-screen__soon-icon"><Icon name="video" size={28} /></span>
          <h2>Yakında</h2>
          <p>Video üretimi henüz hazır değil. Hazır olduğunda burada, görsel üretimiyle aynı akışta açılacak.</p>
          <button onClick={() => onSelect("image-create")} type="button">Görsel üretimine geç</button>
        </section>
      )}
    </div>
  );
}
