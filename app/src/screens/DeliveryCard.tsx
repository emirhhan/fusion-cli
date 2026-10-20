import {Button} from "../ui/Button";
import type { DeliveryEvidence } from "../protocol/deliveryEvidence";

/** Gözlenen özet; dosya varlığı veya modelin bitti metni kalite kanıtı değildir. */
export function DeliveryCard({evidence, onOpenFile}: {evidence: DeliveryEvidence; onOpenFile?: (path: string) => void}) {
  const title = evidence.kind === "unsupported" ? "Kanıt sürümü desteklenmiyor" :
    evidence.kind === "invalid" ? "Kanıt kaydı okunamadı" :
    evidence.falseClaim ? "Başarı iddiası kanıtla uyuşmuyor" :
    evidence.blocking ? "Doğrulama geçmedi" :
    evidence.kind === "legacy" ? "Eski ve sınırlı kanıt kaydı" :
    evidence.verified === true ? "Bildirilen kontroller geçti" : "Teslim doğrulanmadı";
  return <section aria-label="Kanıt özeti" className="delivery-card">
    <strong>{title}</strong>
    {evidence.problems.length > 0 && <ul>{evidence.problems.map((problem, index) => <li key={index}>{problem}</li>)}</ul>}
    {evidence.changed.length > 0 && <details>
      <summary>Değişen dosyalar ({evidence.changed.length})</summary>
      <ul>{evidence.changed.map((path) => <li key={path}>{onOpenFile ? <Button variant="ghost" onClick={() => onOpenFile(path)} aria-label={`${path} dosyasını aç`}><code>{path}</code></Button> : <code>{path}</code>}</li>)}</ul>
    </details>}
    {evidence.changedTotal !== null && evidence.changedTotal > evidence.changed.length &&
      <p>{evidence.changedTotal} dosyanın {evidence.changed.length} tanesi gösteriliyor</p>}
  </section>;
}
