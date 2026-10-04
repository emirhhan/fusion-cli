import { useEffect, useState, type ReactNode } from "react";
import type { MainSection } from "../screens/MainRail";
import "./MainSurface.css";

/** Home ve Görsel/Video kabuğun içinde yaşar; bu üçü tüm yüzeyi kaplar. */
export type SurfaceSection = Extract<MainSection, "scheduled" | "library" | "kits">;

interface MainSurfaceProps {
  kits: ReactNode;
  library: ReactNode;
  scheduled: ReactNode;
  section: SurfaceSection | null;
}

/** Bir kez açılan bölüm DOM'da kalır: Kits sohbeti ve liste konumu menü
 * geçişinde kaybolmaz. Hiç açılmayan bölüm hiç kurulmaz (Kits yan süreci
 * yalnız kullanıcı Kits'e girince başlar). */
export function MainSurface({ kits, library, scheduled, section }: MainSurfaceProps) {
  const [opened, setOpened] = useState<ReadonlySet<SurfaceSection>>(() => new Set());
  useEffect(() => {
    if (section) setOpened((current) => (current.has(section) ? current : new Set(current).add(section)));
  }, [section]);
  const panes: Record<SurfaceSection, ReactNode> = { scheduled, library, kits };
  return (
    <>
      {(Object.keys(panes) as SurfaceSection[]).map((id) =>
        opened.has(id) || section === id ? (
          <section className="main-surface" data-section={id} hidden={section !== id} key={id}>
            {panes[id]}
          </section>
        ) : null,
      )}
    </>
  );
}
