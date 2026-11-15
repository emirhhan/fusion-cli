import {Button} from "../ui/Button";
import { deliveryVerificationState, type DeliveryEvidence } from "../protocol/deliveryEvidence";

/** Gözlenen özet; dosya varlığı veya modelin bitti metni kalite kanıtı değildir. */
export function DeliveryCard({evidence, onOpenFile}: {evidence: DeliveryEvidence; onOpenFile?: (path: string) => void}) {
  const verification = deliveryVerificationState(evidence);
  if (verification === "empty") return null;
  const incomplete = verification === "incomplete";
  const documentPresentation = verification === "passed" && evidence.presentation === "document" && evidence.kind === "supported" &&
    evidence.verified === true && !evidence.blocking && !evidence.falseClaim && !evidence.problems.length &&
    !evidence.unmeasured?.length;
  const documentDetails = documentPresentation &&
    (!!evidence.checks?.length || !!evidence.advisories?.length || !!evidence.changeSummary?.length || evidence.detailsTruncated);
  const title = evidence.falseClaim ? "Başarı iddiası kanıtla uyuşmuyor" :
    evidence.kind === "unsupported" ? "Kanıt sürümü desteklenmiyor" :
    evidence.kind === "invalid" ? "Kanıt kaydı okunamadı" :
    verification === "failed" ? "Doğrulama geçmedi" :
    incomplete ? "Doğrulama tamamlanamadı" :
    evidence.kind === "legacy" ? "Eski ve sınırlı kanıt kaydı" :
    evidence.unmeasured?.length ? "Bazı kontroller ölçülemedi" :
    evidence.deliveryKind === "observation" ? "İşlem kaydı" :
    evidence.deliveryKind === "artifact" && evidence.verified !== true ? "Görsel / belge sonucu ölçülmedi" :
    evidence.verified === true ? (documentPresentation ? `Dosya / önizleme kontrolleri${evidence.warnings?.length ? " · kontrol notu var" : ""}` : "Bildirilen kontroller geçti") : "Teslim doğrulanmadı";
  return <section aria-label="Kanıt özeti" className="delivery-card">
    <strong>{title}</strong>
    {evidence.falseClaim && evidence.kind === "invalid" && <p>Kanıt kaydı okunamadı</p>}
    {evidence.problems.length > 0 && <ul>{evidence.problems.map((problem, index) => <li key={index}>{problem}</li>)}</ul>}
    {(evidence.warnings?.length ?? 0) > 0 && <ul aria-label="Ölçüm eksikleri ve uyarılar">
      {evidence.warnings?.map((warning, index) => <li key={index}>{warning}</li>)}
    </ul>}
    {!incomplete && (evidence.unmeasured?.length ?? 0) > 0 && <ul aria-label="Ölçülemeyen kontroller">
      {evidence.unmeasured?.map((item, index) => <li key={index}>{item}</li>)}
    </ul>}
    {incomplete && <details className="delivery-card__details">
      <summary>Doğrulama ayrıntıları</summary>
      <div className="delivery-card__detail-content" role="region" aria-label="Doğrulama ayrıntıları" tabIndex={0}>
        {!!evidence.unmeasured?.length && <ul aria-label="Ölçülemeyen kontroller">{evidence.unmeasured.map((item, index) => <li key={index}>{item}</li>)}</ul>}
        {!evidence.unmeasured?.length && <p>{evidence.blocking
          ? "Doğrulama engellendi; neden veya kontrol sonucu bildirilmedi."
          : "Doğrulamanın tamamlandığını gösteren yeterli kontrol sonucu yok."}</p>}
        {!!evidence.checks?.length && <ul aria-label="Geçen kontroller">{evidence.checks.map((item, index) => <li key={index}>{item}</li>)}</ul>}
        {!!evidence.advisories?.length && <ul aria-label="Öneriler">{evidence.advisories.map((item, index) => <li key={index}>{item}</li>)}</ul>}
        {!!evidence.changeSummary?.length && <ul aria-label="Gerçek değişiklik özeti">{evidence.changeSummary.map((item, index) => <li key={index}>{item}</li>)}</ul>}
      </div>
    </details>}
    {documentDetails && <details className="delivery-card__details">
      <summary>Dosya / önizleme kontrol ayrıntıları</summary>
      <div className="delivery-card__detail-content" role="region" aria-label="Dosya / önizleme kontrol ayrıntıları" tabIndex={0}>
        {!!evidence.checks?.length && <ul aria-label="Geçen kontroller">{evidence.checks.map((item, index) => <li key={index}>{item}</li>)}</ul>}
        {!!evidence.advisories?.length && <ul aria-label="Öneriler">{evidence.advisories.map((item, index) => <li key={index}>{item}</li>)}</ul>}
        {!!evidence.changeSummary?.length && <ul aria-label="Gerçek değişiklik özeti">{evidence.changeSummary.map((item, index) => <li key={index}>{item}</li>)}</ul>}
        {evidence.detailsTruncated && <p>Bazı ayrıntılar gösterim sınırları nedeniyle kısaltıldı.</p>}
      </div>
    </details>}
    {evidence.detailsTruncated && !documentDetails && <p>Bazı ayrıntılar gösterim sınırları nedeniyle kısaltıldı.</p>}
    {evidence.changed.length > 0 && <details>
      <summary>Değişen dosyalar ({evidence.changed.length})</summary>
      <ul>{evidence.changed.map((path) => <li key={path}>{onOpenFile ? <Button variant="ghost" onClick={() => onOpenFile(path)} aria-label={`${path} dosyasını aç`}><code>{path}</code></Button> : <code>{path}</code>}</li>)}</ul>
    </details>}
    {evidence.changedTotal !== null && evidence.changedTotal > evidence.changed.length &&
      <p>{evidence.changedTotal} dosyanın {evidence.changed.length} tanesi gösteriliyor</p>}
  </section>;
}
