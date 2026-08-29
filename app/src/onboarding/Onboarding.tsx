import { useEffect, useRef, type ReactNode } from "react";
import type {
  DiscoveredSource,
  OnboardingCompletion,
  OnboardingStepId,
  OnboardingValue,
  ProviderSummary,
  RuntimeSummary,
  SampleProject,
} from "./types";
import { Button } from "../ui/Button";
import { StatusRow } from "../ui/StatusRow";
import "../theme/tokens.css";
import "./Onboarding.css";

const STEPS: OnboardingStepId[] = [
  "welcome",
  "runtime",
  "sources",
  "providers",
  "project",
  "complete",
];

const STEP_LABELS: Record<OnboardingStepId, string> = {
  welcome: "Hoş geldiniz",
  runtime: "Çalışma zamanı",
  sources: "Kaynaklar",
  providers: "Sağlayıcılar",
  project: "Örnek proje",
  complete: "Tamamlandı",
};

const SOURCE_LABELS: Record<DiscoveredSource["kind"], string> = {
  claude: "Claude",
  codex: "Codex",
  hermes: "Hermes",
};

const PROVIDER_STATUSES: Record<
  ProviderSummary["status"],
  { label: string; tone: "success" | "warning" | "neutral" }
> = {
  ready: { label: "Hazır", tone: "success" },
  "needs-setup": { label: "Kurulum gerekli", tone: "warning" },
  unavailable: { label: "Kullanılamıyor", tone: "neutral" },
};

const SECRET_PATTERNS = [
  /\bsk-(?:ant-)?[A-Za-z0-9_-]{12,}\b/g,
  /\bgh[oprsu]_[A-Za-z0-9]{20,}\b/g,
  /\bAIza[A-Za-z0-9_-]{20,}\b/g,
  /\b(?:api[_-]?key|token|secret)\s*[:=]\s*[^\s,;]+/gi,
];

function redactExternalText(value: string): string {
  return SECRET_PATTERNS.reduce(
    (safeValue, pattern) => safeValue.replace(pattern, "[gizlendi]"),
    value,
  );
}

export interface OnboardingProps {
  onChange: (value: OnboardingValue) => void;
  onComplete: (completion: OnboardingCompletion) => void;
  onSkip: (value: OnboardingValue) => void;
  projects: SampleProject[];
  providers: ProviderSummary[];
  runtime: RuntimeSummary;
  sources: DiscoveredSource[];
  value: OnboardingValue;
}

function WelcomeStep() {
  return (
    <>
      <p className="onboarding__eyebrow">Fusion for macOS</p>
      <h1>Fusion'a hoş geldiniz</h1>
      <p className="onboarding__lead">
        Yerel araçlarınızı ve model sağlayıcılarınızı tek bir çalışma alanında kullanmaya başlayın.
      </p>
    </>
  );
}

function RuntimeStep({ runtime }: { runtime: RuntimeSummary }) {
  const headings: Record<RuntimeSummary["status"], string> = {
    checking: "Çalışma zamanı denetleniyor",
    ready: "Çalışma zamanı hazır",
    repairable: "Çalışma zamanı onarılmalı",
    error: "Çalışma zamanı kullanılamıyor",
  };

  return (
    <>
      <p className="onboarding__eyebrow">Yerel ve bağımsız</p>
      <h1>{headings[runtime.status]}</h1>
      <p className="onboarding__lead">
        {runtime.status === "ready"
          ? "Fusion yerel çalışma zamanı kullanıma hazır."
          : "Fusion yerel çalışma zamanının durumu uygulama tarafından denetleniyor."}
      </p>
      {runtime.version && <p className="onboarding__meta">Sürüm {redactExternalText(runtime.version)}</p>}
    </>
  );
}

function SourcesStep({ sources }: { sources: DiscoveredSource[] }) {
  return (
    <>
      <p className="onboarding__eyebrow">Yerel keşif</p>
      <h1>Kaynaklarınız bulundu</h1>
      <p className="onboarding__lead">Fusion yalnız bilgisayarınızda keşfedilen araçların özetini gösterir.</p>
      <div className="onboarding__status-list">
        {sources.map((source) => (
          <StatusRow
            description={source.status === "found" ? "Yerel kaynak" : "Bu Mac'te keşfedilmedi"}
            key={source.kind}
            label={SOURCE_LABELS[source.kind]}
            status={source.status === "found" ? `${source.itemCount ?? 0} öğe` : "Bulunamadı"}
            tone={source.status === "found" ? "success" : "neutral"}
          />
        ))}
      </div>
    </>
  );
}

function ProvidersStep({ providers }: { providers: ProviderSummary[] }) {
  return (
    <>
      <p className="onboarding__eyebrow">Bağlantılar</p>
      <h1>Sağlayıcı durumu</h1>
      <p className="onboarding__lead">Anahtar değerleri Fusion onboarding arayüzüne aktarılmaz veya gösterilmez.</p>
      <div className="onboarding__status-list">
        {providers.map((provider) => {
          const status = PROVIDER_STATUSES[provider.status];
          return (
            <StatusRow
              description={provider.secretConfigured ? "Kimlik bilgisi yapılandırıldı" : "Kimlik bilgisi eklenmedi"}
              key={provider.id}
              label={redactExternalText(provider.name)}
              status={status.label}
              tone={status.tone}
            />
          );
        })}
      </div>
    </>
  );
}

function ProjectStep({
  onSelect,
  projects,
  selectedProjectId,
}: {
  onSelect: (projectId: string) => void;
  projects: SampleProject[];
  selectedProjectId: string | null;
}) {
  return (
    <>
      <p className="onboarding__eyebrow">İlk çalışma alanı</p>
      <h1>Bir örnek proje seçin</h1>
      <p className="onboarding__lead">İsterseniz bu adımı atlayıp daha sonra kendi klasörünüzü açabilirsiniz.</p>
      <div className="onboarding__project-list">
        {projects.map((project) => (
          <button
            aria-pressed={selectedProjectId === project.id}
            className="onboarding__project"
            data-selected={selectedProjectId === project.id}
            key={project.id}
            onClick={() => onSelect(project.id)}
            type="button"
          >
            <strong>{redactExternalText(project.name)}</strong>
            <span>{redactExternalText(project.description)}</span>
            {project.path && <code>{redactExternalText(project.path)}</code>}
          </button>
        ))}
      </div>
    </>
  );
}

function CompleteStep({ project }: { project?: SampleProject }) {
  return (
    <>
      <p className="onboarding__eyebrow">Kurulum tamamlandı</p>
      <h1>Fusion hazır</h1>
      <p className="onboarding__lead">
        {project
          ? `${redactExternalText(project.name)} ile başlamaya hazırsınız.`
          : "İlk çalışma alanınızı açmaya hazırsınız."}
      </p>
    </>
  );
}

export function Onboarding({
  onChange,
  onComplete,
  onSkip,
  projects,
  providers,
  runtime,
  sources,
  value,
}: OnboardingProps) {
  const contentRef = useRef<HTMLDivElement>(null);
  const stepIndex = STEPS.indexOf(value.step);
  const selectedProject = projects.find((project) => project.id === value.selectedProjectId);

  const move = (offset: -1 | 1) => {
    const step = STEPS[stepIndex + offset];
    if (step) onChange({ ...value, step });
  };

  useEffect(() => {
    const heading = contentRef.current?.querySelector("h1");
    if (!heading) return;
    heading.tabIndex = -1;
    heading.focus();
  }, [value.step]);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (!event.altKey || event.ctrlKey || event.metaKey) return;
      const offset = event.key === "ArrowLeft" ? -1 : event.key === "ArrowRight" ? 1 : 0;
      if (offset === 0) return;
      if (offset === 1 && value.step === "project" && value.selectedProjectId === null) return;
      const step = STEPS[stepIndex + offset];
      if (!step) return;
      event.preventDefault();
      onChange({ ...value, step });
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onChange, stepIndex, value]);

  const content = {
    welcome: <WelcomeStep />,
    runtime: <RuntimeStep runtime={runtime} />,
    sources: <SourcesStep sources={sources} />,
    providers: <ProvidersStep providers={providers} />,
    project: (
      <ProjectStep
        onSelect={(selectedProjectId) => onChange({ ...value, selectedProjectId })}
        projects={projects}
        selectedProjectId={value.selectedProjectId}
      />
    ),
    complete: <CompleteStep project={selectedProject} />,
  } satisfies Record<OnboardingStepId, ReactNode>;

  return (
    <main className="onboarding">
      <aside aria-label="Kurulum adımları" className="onboarding__rail">
        <div aria-hidden="true" className="onboarding__brand-mark"><span /><span /></div>
        <ol>
          {STEPS.map((step, index) => (
            <li aria-current={step === value.step ? "step" : undefined} data-complete={index < stepIndex} key={step}>
              <span aria-hidden="true">{index + 1}</span>
              {STEP_LABELS[step]}
            </li>
          ))}
        </ol>
      </aside>
      <section className="onboarding__panel">
        <div className="onboarding__content" ref={contentRef}>{content[value.step]}</div>
        <footer className="onboarding__footer">
          <div>
            {stepIndex > 0 && <Button onClick={() => move(-1)} variant="ghost">Geri</Button>}
          </div>
          <div className="onboarding__actions">
            {value.step !== "complete" && <Button onClick={() => onSkip(value)} variant="ghost">Şimdilik atla</Button>}
            {value.step === "complete" ? (
              <Button
                onClick={() => onComplete({ selectedProjectId: value.selectedProjectId })}
                variant="primary"
              >
                Fusion'ı aç
              </Button>
            ) : (
              <Button
                disabled={value.step === "project" && value.selectedProjectId === null}
                onClick={() => move(1)}
                variant="primary"
              >
                İleri
              </Button>
            )}
          </div>
        </footer>
      </section>
    </main>
  );
}
