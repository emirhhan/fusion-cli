import type { Soru } from "../protocol/types";

interface ApprovalProps {
  soru: Soru;
  onCevap: (veri: Record<string, unknown>) => void;
}

/** Çekirdeğin onay sözleşmesini değiştirmeden kullanıcıya gösterir. */
export function Approval({ soru, onCevap }: ApprovalProps) {
  const argumentsList = Object.entries(soru.argumanlar ?? {});
  return (
    <section
      aria-labelledby="approval-title"
      role="dialog"
      style={{
        background: "var(--zemin)",
        border: "1px solid var(--kenarlik)",
        borderRadius: "var(--yaricap)",
        color: "var(--ana-metin)",
        maxWidth: 480,
        padding: 20,
      }}
    >
      <h2 id="approval-title" style={{ fontSize: 16, margin: "0 0 8px" }}>
        Bu işleme izin verilsin mi?
      </h2>
      <div style={{ fontFamily: "monospace", fontSize: 13, marginBottom: 12 }}>
        <div>{soru.arac}</div>
        {argumentsList.length > 0 && (
          <div style={{ color: "var(--sonuk-metin)", marginTop: 4 }}>
            {argumentsList.map(([key, value]) => `${key}: ${value}`).join("  ·  ")}
          </div>
        )}
      </div>
      {soru.tehlike && (
        <div style={{ color: "var(--tehlike)", fontSize: 13, marginBottom: 12 }}>
          ⚠ {soru.tehlike}
        </div>
      )}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
        {(soru.secenekler ?? []).map((secenek) => (
          <button
            key={secenek.deger ?? secenek.etiket}
            onClick={() => onCevap({ secim: secenek.deger })}
            style={{
              background: secenek.deger === "deny" ? "var(--zemin)" : "var(--birincil-buton)",
              border: "1px solid var(--kenarlik)",
              borderRadius: 999,
              color: secenek.deger === "deny" ? "var(--ana-metin)" : "var(--ters-metin)",
              cursor: "pointer",
              padding: "8px 14px",
            }}
            type="button"
          >
            {secenek.etiket}
          </button>
        ))}
      </div>
    </section>
  );
}
