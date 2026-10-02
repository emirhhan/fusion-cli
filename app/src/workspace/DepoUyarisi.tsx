import "./DepoUyarisi.css";

/**
 * Kök bir proje DEPOSUYSA (Masaüstü gibi, içinde birden çok proje) uyarı şeridi.
 *
 * Ölçüldü (1 Ekim olayı): Fusion `~/Desktop`'ta açıktı; "projeyi tamamiyle sil"
 * isteğinde ajan için "proje" Masaüstünün tamamıydı. Kullanıcı neyin içinde
 * çalıştığını görmeli ve tek bir projeyi tek tıkla açabilmeli.
 */

/** Şeritte doğrudan açılabilecek en fazla proje; gerisi sayıyla belirtilir. */
const GOSTERILEN = 4;

export interface DepoUyarisiProps {
  kok: string;
  projeler: string[];
  onAc: (kok: string) => void;
}

export function DepoUyarisi({ kok, projeler, onAc }: DepoUyarisiProps) {
  if (projeler.length === 0) return null;
  const gosterilen = projeler.slice(0, GOSTERILEN);
  const kalan = projeler.length - gosterilen.length;
  const ayirici = kok.includes("\\") && !kok.includes("/") ? "\\" : "/";
  return (
    <aside aria-label="Proje deposu uyarısı" className="depo-uyarisi" role="note">
      <p className="depo-uyarisi__metin">
        <strong>Bu klasör tek bir proje değil</strong> — içinde {projeler.length} proje var. Ajan
        &quot;proje&quot; dediğinde hangisini kastettiğini soracak. Tek bir projede çalışmak için aç:
      </p>
      <div className="depo-uyarisi__projeler">
        {gosterilen.map((proje) => (
          <button
            className="depo-uyarisi__proje"
            key={proje}
            onClick={() => onAc(`${kok.replace(/[\\/]+$/, "")}${ayirici}${proje}`)}
            title={proje}
            type="button"
          >
            {proje.split("/").pop()}
          </button>
        ))}
        {kalan > 0 && <span className="depo-uyarisi__kalan">+{kalan} proje</span>}
      </div>
    </aside>
  );
}
