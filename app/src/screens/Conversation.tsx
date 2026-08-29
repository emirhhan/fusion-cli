export interface Mesaj {
  rol: "kullanici" | "asistan" | "olay";
  metin: string;
}

/**
 * Kullanıcı ve asistan mesajları SİMETRİK DEĞİLDİR.
 *
 * Ölçüldü: kullanıcı mesajı sağa hizalı kabarcık, asistan mesajı kabarcıksız
 * tam genişlikte metin. İki taraflı kabarcık düzeni referansın görünümünü bozar.
 */
export function Conversation({ mesajlar }: { mesajlar: Mesaj[] }) {
  return (
    <div style={{ flex: 1, overflowY: "auto", padding: "24px 0" }}>
      <div style={{ maxWidth: "var(--icerik-en-fazla)", margin: "0 auto", padding: "0 16px" }}>
        {mesajlar.map((m, i) => (
          <div key={i} style={{ marginBottom: 20, display: "flex", justifyContent: m.rol === "kullanici" ? "flex-end" : "flex-start" }}>
            {m.rol === "kullanici" ? (
              <div style={{ background: "var(--kullanici-balonu)", borderRadius: "var(--yaricap)", padding: "10px 16px", maxWidth: "82%" }}>
                {m.metin}
              </div>
            ) : m.rol === "olay" ? (
              <div style={{ color: "var(--sonuk-metin)", fontSize: 13 }}>{m.metin}</div>
            ) : (
              <div style={{ width: "100%", lineHeight: 1.65 }}>{m.metin}</div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
