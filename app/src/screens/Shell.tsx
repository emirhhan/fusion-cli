import type { ReactNode } from "react";
import "../theme/tokens.css";

/** Sol kenar çubuğu sabit genişlikte, içerik alanı esnek. Ölçülmüş düzen. */
export function Shell({ kenar, icerik }: { kenar: ReactNode; icerik: ReactNode }) {
  return (
    <div style={{ display: "flex", height: "100vh", background: "var(--zemin)" }}>
      <aside
        style={{
          width: "var(--kenar-cubugu-genislik)",
          flexShrink: 0,
          background: "var(--kenar-cubugu)",
          borderRight: "1px solid var(--kenarlik)",
          overflowY: "auto",
        }}
      >
        {kenar}
      </aside>
      <main style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
        {icerik}
      </main>
    </div>
  );
}
