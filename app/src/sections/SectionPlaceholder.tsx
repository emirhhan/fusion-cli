interface SectionPlaceholderProps {
  detail: string;
  title: string;
}

/** Bölümün gerçek ekranı bağlanana kadar görünen dürüst boş durum. */
export function SectionPlaceholder({ detail, title }: SectionPlaceholderProps) {
  return (
    <div className="empty-state">
      <div className="empty-state__content">
        <h2>{title}</h2>
        <p>{detail}</p>
      </div>
    </div>
  );
}
