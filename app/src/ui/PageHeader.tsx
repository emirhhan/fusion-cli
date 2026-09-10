import type { ReactNode } from "react";
import "./PageHeader.css";

interface PageHeaderProps {
  /** Başlığın üstündeki bağlam etiketi ("TERCİHLER", "Fusion for macOS"). */
  eyebrow?: string;
  /** Sayfanın kendi kimliği. Uygulama başlığı bunu TEKRARLAMAZ. */
  title: string;
  description?: string;
  /** Sağ tarafa yerleşen eylemler: kapat düğmesi, arama alanı. */
  actions?: ReactNode;
}

/** Tam ekran sayfaların ortak başlığı.
 *
 * Ayarlar ve Kontrol Paneli bu başlığı AYRI AYRI yazıyordu: aynı yapı iki farklı
 * CSS'te, farklı yazı boyutu ve farklı harf aralığıyla duruyordu. Aynı üründe iki
 * tasarım dili demekti. Tek kaynak burasıdır; ölçüler yalnız tasarım tokenlarından
 * gelir, bileşenler ham piksel yazmaz.
 */
export function PageHeader({ eyebrow, title, description, actions }: PageHeaderProps) {
  return (
    <header className="page-header">
      <div className="page-header__identity">
        {eyebrow && <span className="page-header__eyebrow">{eyebrow}</span>}
        <h2 className="page-header__title">{title}</h2>
        {description && <p className="page-header__description">{description}</p>}
      </div>
      {actions && <div className="page-header__actions">{actions}</div>}
    </header>
  );
}
