import { useState } from "react";
import type { ComposerAttachment } from "./Composer";
import { assetUrl } from "../platform/assetUrl";

/**
 * Ek rozeti.
 *
 * Görsel ekler için küçük bir ÖNİZLEME gösterilir: kullanıcı dosya adına
 * bakarak hangi görseli eklediğini ayırt edemiyordu. Önizleme yüklenemezse
 * (kabuk yok, dosya okunamıyor) sessizce simgeye düşülür; kırık bir görsel
 * kutusu göstermek yanlış bilgi verirdi.
 */
export function AttachmentChip({
  attachment,
  onRemove,
}: {
  attachment: ComposerAttachment;
  onRemove: () => void;
}) {
  const [bozuk, setBozuk] = useState(false);
  const kaynak = attachment.kind === "image" && !bozuk ? assetUrl(attachment.path) : null;

  return (
    <span className="composer__attachment" data-gorsel={Boolean(kaynak)}>
      {kaynak ? (
        <img
          alt={`${attachment.name} önizlemesi`}
          className="composer__attachment-thumb"
          height={28}
          onError={() => setBozuk(true)}
          src={kaynak}
          width={28}
        />
      ) : (
        <span aria-hidden="true">{attachment.kind === "image" ? "▧" : "▤"}</span>
      )}
      <span>{attachment.name}</span>
      <button aria-label={`${attachment.name} ekini kaldır`} onClick={onRemove} type="button">
        ×
      </button>
    </span>
  );
}
