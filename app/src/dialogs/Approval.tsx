import { useEffect, useRef, type KeyboardEvent } from "react";
import type { Soru } from "../protocol/types";
import { Button } from "../ui/Button";
import "./Approval.css";

interface ApprovalProps {
  onCevap: (veri: Record<string, unknown>) => void;
  soru: Soru;
}

export function Approval({ soru, onCevap }: ApprovalProps) {
  const dialogRef = useRef<HTMLElement>(null);
  const argumentsList = Object.entries(soru.argumanlar ?? {});
  const deny = soru.secenekler?.find((option) => option.deger === "deny");
  const recommended = soru.onerilen ?? soru.secenekler?.find((option) => option.deger !== "deny")?.deger;

  useEffect(() => {
    dialogRef.current?.focus();
  }, []);

  const onKeyDown = (event: KeyboardEvent<HTMLElement>) => {
    if (event.key === "Escape" && deny) {
      event.preventDefault();
      onCevap({ secim: deny.deger });
    }
  };

  return (
    <div className="approval-backdrop">
      <section
        aria-labelledby="approval-title"
        aria-modal="true"
        className="approval"
        onKeyDown={onKeyDown}
        ref={dialogRef}
        role="dialog"
        tabIndex={-1}
      >
        <div className="approval__eyebrow">İzin gerekiyor</div>
        <h2 id="approval-title">Bu işleme izin verilsin mi?</h2>
        <p className="approval__explanation">Fusion aşağıdaki aracı belirtilen kapsamda çalıştırmak istiyor.</p>
        <div className="approval__tool">
          <strong>{soru.arac}</strong>
          {argumentsList.length > 0 && (
            <dl>
              {argumentsList.map(([key, value]) => (
                <div key={key}><dt>{key}</dt><dd>{String(value)}</dd></div>
              ))}
            </dl>
          )}
        </div>
        {soru.tehlike && <p className="approval__danger">Dikkat: {soru.tehlike}</p>}
        <div className="approval__actions">
          {(soru.secenekler ?? []).map((option) => {
            const isRecommended = option.deger === recommended;
            return (
              <Button
                data-recommended={isRecommended || undefined}
                key={option.deger ?? option.etiket}
                onClick={() => onCevap({ secim: option.deger })}
                variant={isRecommended ? "primary" : option.deger === "deny" ? "ghost" : "secondary"}
              >
                {option.etiket}
              </Button>
            );
          })}
        </div>
      </section>
    </div>
  );
}
