/**
 * Konuşma başlamadığında gösterilen boş durum ekranı.
 */
export function EmptyState() {
  return (
    <div
      style={{
        flex: 1,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "24px",
        textAlign: "center",
      }}
    >
      <div>
        <h2 style={{ color: "var(--ana-metin)", marginBottom: "12px", fontSize: 18 }}>
          Başlamaya hazır mısın?
        </h2>
        <p style={{ color: "var(--sonuk-metin)", fontSize: 14, lineHeight: 1.6 }}>
          Bir görev veya soru yazarak başla. Asistan cevaplarını ve yapılan işlemleri burada göreceksin.
        </p>
      </div>
    </div>
  );
}
