export interface OturumSatiri {
  session_id: string;
  title: string;
  source: string;
}

interface SidebarProps {
  oturumlar: OturumSatiri[];
  etkin: string | null;
  onSec: (id: string) => void;
  onYeni: () => void;
}

function SessionButton({ session, active, onSelect }: {
  session: OturumSatiri;
  active: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      data-etkin={active}
      onClick={onSelect}
      style={{
        background: active ? "var(--secili-satir)" : "transparent",
        border: "none",
        borderRadius: 8,
        cursor: "pointer",
        fontSize: 14,
        padding: "8px 10px",
        textAlign: "left",
      }}
      type="button"
    >
      <div style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
        {session.title}
      </div>
      <div style={{ color: "var(--sonuk-metin)", fontSize: 11 }}>[{session.source}]</div>
    </button>
  );
}

/** Oturum yoksa boş bir "Sohbetler" bölümü göstermez. */
export function Sidebar({ oturumlar, etkin, onSec, onYeni }: SidebarProps) {
  return (
    <nav aria-label="Sohbetler" style={{ display: "flex", flexDirection: "column", gap: 4, padding: 12 }}>
      <button
        onClick={onYeni}
        style={{ background: "transparent", border: "none", borderRadius: 8, cursor: "pointer", fontSize: 14, padding: "8px 10px", textAlign: "left" }}
        type="button"
      >
        Yeni sohbet
      </button>
      {oturumlar.length > 0 && (
        <>
          <div style={{ color: "var(--sonuk-metin)", fontSize: 12, padding: "12px 10px 4px" }}>
            Sohbetler
          </div>
          {oturumlar.map((session) => (
            <SessionButton
              active={session.session_id === etkin}
              key={session.session_id}
              onSelect={() => onSec(session.session_id)}
              session={session}
            />
          ))}
        </>
      )}
    </nav>
  );
}
