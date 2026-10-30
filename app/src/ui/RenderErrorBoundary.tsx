import { Component, type ErrorInfo, type ReactNode } from "react";

/**
 * Render sırasında atılan istisnanın bütün pencereyi boşaltmasını önler (U6-32).
 * `useCrashReporter` yalnız `error`/`unhandledrejection` olaylarını dinler; React render
 * hataları kökte yakalanmazsa ağaç söker ve kullanıcı boş pencereyle kalır.
 * (Hata sınırları yalnızca sınıf bileşeniyle yazılabilir.)
 */
export class RenderErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError(): { failed: boolean } {
    return { failed: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error("Arayüz çizilemedi", error, info.componentStack);
  }

  render(): ReactNode {
    if (!this.state.failed) return this.props.children;
    return (
      <main role="alert" style={{ padding: "48px 24px", textAlign: "center" }}>
        <h1 style={{ fontSize: 18, marginBottom: 8 }}>Fusion arayüzü çizilemedi</h1>
        <p style={{ marginBottom: 16 }}>Beklenmeyen bir hata oluştu. Pencereyi yenileyince çoğu zaman düzelir.</p>
        <button onClick={() => window.location.reload()} type="button">Yeniden yükle</button>
      </main>
    );
  }
}
