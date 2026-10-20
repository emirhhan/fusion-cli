import { useEffect, useRef, type ReactNode } from "react";
import type {
  ApprenticeStatus,
  DiscoveredSource,
  OnboardingCompletion,
  OnboardingStepId,
  OnboardingValue,
  ProviderSummary,
  RuntimeSummary,
  SampleProject,
} from "./types";
import type { AsyncState } from "../protocol/asyncState";
import { Logo } from "../brand/Logo";
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
  "guide",
  "complete",
];

const STEP_LABELS: Record<OnboardingStepId, string> = {
  welcome: "Hoş geldiniz",
  runtime: "Çalışma zamanı",
  sources: "Kaynaklar",
  providers: "Sağlayıcılar",
  project: "Örnek proje",
  guide: "Eğitim",
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
  "configured-unverified": { label: "Yapılandırıldı · doğrulanmadı", tone: "warning" },
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
  /** Ücretsiz API çırağı şu an etkin mi? Yoksa: `providers` sağlayıcı butonuyla döner. */
  apprentice: ApprenticeStatus;
  onChange: (value: OnboardingValue) => void;
  onComplete: (completion: OnboardingCompletion) => void;
  /** Kullanıcı "ücretsiz çırağa dön" düğmesine bastığında; kalıcılaştırma çağıranın işidir. */
  onResetToApprentice: () => void;
  onSkip: (value: OnboardingValue) => void;
  projects: SampleProject[];
  providers: ProviderSummary[];
  runtime: RuntimeSummary;
  sources: DiscoveredSource[];
  value: OnboardingValue;
  sourcesState?: AsyncState<DiscoveredSource[]>;
  controlState?: AsyncState<unknown>;
  controlHasSnapshot?: boolean;
  onRetrySources?: () => void;
  onRetryControl?: () => void;
  onConnectProvider?: (id: string) => void;
  resetPending?: boolean;
  resetError?: string | null;
  /** "Eğitim" adımının içeriği; verilmezse adım atlanabilir bir bilgi metni gösterir. */
  guide?: ReactNode;
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
      <h1>{sources.some((source) => source.status === "found") ? "Kaynaklarınız bulundu" : "İçe aktarılacak sohbet bulunamadı"}</h1>
      <p className="onboarding__lead">Bu kullanıcı profilindeki Claude, Codex ve Hermes sohbetleri aranır. Geçmiş bulunmaması Fusion kullanmanı engellemez; bu adımı atlayabilirsin.</p>
      <div className="onboarding__status-list">
        {sources.map((source) => (
          <StatusRow
            description={source.status === "found" ? "Yerel kaynak" : "Bu Mac'te keşfedilmedi"}
            key={source.kind}
            label={SOURCE_LABELS[source.kind]}
            status={source.status === "found" ? (source.itemCount === undefined ? "Bulundu" : `${source.itemCount} öğe`) : "Bulunamadı"}
            tone={source.status === "found" ? "success" : "neutral"}
          />
        ))}
      </div>
    </>
  );
}

function ApprenticeStatusRow({
  apprentice,
  onResetToApprentice,
  resetPending,
}: {
  resetPending?: boolean;
  apprentice: ApprenticeStatus;
  onResetToApprentice: () => void;
}) {
  // Faz 3, Görev 2 (C5/C9): agent bir web modeline kilitliyken bunu SESSİZCE
  // değiştirmeyiz (bkz. `config/model_select.py::reset_to_apprentice_default`
  // docstring'i) — yalnızca burada, panelde kalıcı bir düğme sunarız. Web
  // modeli kötülenmez: çalıştığı söylenir, somut fark (hız + gerçek araç
  // çağrısı) belirtilir.
  if (apprentice.active === null) return <StatusRow label="Ücretsiz API çırağı" status="Durumu bilinmiyor" tone="neutral" />;
  if (apprentice.active) {
    return (
      <StatusRow
        description="Her tur gerçek araç çağrısı yapan ücretsiz bir API modeli çalışıyor."
        label="Ücretsiz API çırağı"
        status="Etkin"
        tone="success"
      />
    );
  }
  return (
    <StatusRow
      action={
        <Button disabled={resetPending} onClick={onResetToApprentice} variant="secondary">
          Ücretsiz çırağa dön
        </Button>
      }
      description={
        apprentice.recommendedModel
          ? `Şu an web modeline bağlısın — çalışıyor, ama her tur tarayıcıya gidip araç çağrısını taklit ediyor. Ücretsiz çırak (${apprentice.recommendedModel}) gerçek araç çağrısı yapıyor ve daha hızlı yanıt veriyor.`
          : "Şu an web modeline bağlısın — çalışıyor, ama her tur tarayıcıya gidip araç çağrısını taklit ediyor."
      }
      label="Ücretsiz API çırağı"
      status="Kullanılmıyor"
      tone="warning"
    />
  );
}

function ProvidersStep({
  apprentice,
  onResetToApprentice,
  providers,
  onConnectProvider,
  resetPending,
}: {
  onConnectProvider?: (id: string) => void;
  resetPending?: boolean;
  apprentice: ApprenticeStatus;
  onResetToApprentice: () => void;
  providers: ProviderSummary[];
}) {
  return (
    <>
      <p className="onboarding__eyebrow">Bağlantılar</p>
      <h1>Sağlayıcı durumu</h1>
      <p className="onboarding__lead">Anahtar değerleri Fusion onboarding arayüzüne aktarılmaz veya gösterilmez.</p>
      <div className="onboarding__status-list">
        <ApprenticeStatusRow apprentice={apprentice} onResetToApprentice={onResetToApprentice} resetPending={resetPending} />
        {providers.map((provider) => {
          const status = PROVIDER_STATUSES[provider.status];
          return (
            <StatusRow
              action={onConnectProvider && <Button onClick={() => onConnectProvider(provider.id)} variant="secondary">Bağlan</Button>}
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
  apprentice,
  onChange,
  onComplete,
  onResetToApprentice,
  onSkip,
  projects,
  providers,
  runtime,
  sources,
  value, sourcesState, controlState, controlHasSnapshot, onRetrySources, onRetryControl, onConnectProvider, resetPending, resetError, guide,
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
    sources: sourcesState?.status === "loading" ? <><h1>Kaynaklar yükleniyor</h1><p role="status">Kaynak keşfi sürüyor.</p></> : sourcesState?.status === "error" ? <><h1>Kaynaklar okunamadı</h1><p role="alert">{sourcesState.message}</p><Button onClick={onRetrySources}>Yeniden dene</Button></> : <SourcesStep sources={sources} />,
    providers: !controlHasSnapshot && controlState?.status === "loading" ? <><h1>Sağlayıcılar yükleniyor</h1><p role="status">Kontrol durumu yükleniyor.</p></> : !controlHasSnapshot && controlState?.status === "error" ? <><h1>Sağlayıcılar okunamadı</h1><p role="alert">{controlState.message}</p><Button onClick={onRetryControl}>Yeniden dene</Button></> : (
      <> {controlHasSnapshot && controlState?.status === "error" && <p role="alert">{controlState.message}<Button onClick={onRetryControl}>Durumu yeniden dene</Button></p>}
      <ProvidersStep
        apprentice={apprentice}
        onResetToApprentice={onResetToApprentice}
        providers={providers}
        onConnectProvider={onConnectProvider}
        resetPending={resetPending}
      /></>
    ),
    project: (
      <ProjectStep
        onSelect={(selectedProjectId) => onChange({ ...value, selectedProjectId })}
        projects={projects}
        selectedProjectId={value.selectedProjectId}
      />
    ),
    guide: guide ?? <><h1>Fusion'ı tanıyın</h1><p className="onboarding__lead">Eğitim konuları Ayarlar → Nasıl yapılır sayfasında.</p></>,
    complete: <CompleteStep project={selectedProject} />,
  } satisfies Record<OnboardingStepId, ReactNode>;

  return (
    <main className="onboarding">
      <aside aria-label="Kurulum adımları" className="onboarding__rail">
        <div aria-hidden="true" className="onboarding__brand-mark"><Logo size={34} /></div>
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
        <div className="onboarding__content" ref={contentRef}>{content[value.step]}{resetError && <p role="alert">{resetError}<Button onClick={onResetToApprentice} disabled={resetPending}>Yeniden dene</Button></p>}</div>
        <footer className="onboarding__footer">
          <div>
            {stepIndex > 0 && <Button onClick={() => move(-1)} variant="ghost">Geri</Button>}
          </div>
          <div className="onboarding__actions">
            {value.step === "project" && <Button onClick={() => onComplete({ selectedProjectId: null })} variant="secondary">Proje seçmeden devam et</Button>}
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
