import {Button} from "../ui/Button";
import type {ReviewFinding} from "../protocol/reviewFindings";

const VERDICT_LABEL: Record<string, string> = {CONFIRMED: "doğrulandı", PLAUSIBLE: "olası"};

/** `/code-review` bulgu kartları (Claude Code ReportFindings, #214); en ciddiden başlar. */
export function FindingsCard({findings, onOpenFile}: {findings: ReviewFinding[]; onOpenFile?: (path: string) => void}) {
  return <section aria-label="İnceleme bulguları" className="findings-card">
    <strong>{findings.length ? `${findings.length} bulgu` : "Doğrulanan bulgu yok"}</strong>
    {findings.length > 0 && <ol>
      {findings.map((item, index) => {
        const location = `${item.file}:${item.line}`;
        return <li key={`${location}-${index}`} className="findings-card__item">
          <div className="findings-card__head">
            {onOpenFile
              ? <Button variant="ghost" onClick={() => onOpenFile(item.file)} aria-label={`${item.file} dosyasını aç`}><code>{location}</code></Button>
              : <code>{location}</code>}
            {item.category && <span className="findings-card__tag">{item.category}</span>}
            {item.verdict && <span className={`findings-card__tag findings-card__tag--${item.verdict.toLowerCase()}`}>{VERDICT_LABEL[item.verdict]}</span>}
          </div>
          <p>{item.summary}</p>
          <details>
            <summary>Hata senaryosu</summary>
            <p>{item.failureScenario}</p>
          </details>
        </li>;
      })}
    </ol>}
  </section>;
}
