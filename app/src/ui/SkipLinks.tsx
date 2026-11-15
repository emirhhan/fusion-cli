import type { MouseEvent } from "react";
import { useLanguage } from "../i18n/useLanguage";

/**
 * Odak atlama bağlantıları (P-065): klavye kullanıcısı Tab'a ilk bastığında görünür,
 * kenar çubuğundaki onlarca düğmeyi geçmeden içeriğe ya da mesaj kutusuna iner.
 * Hedefin içindeki ilk odaklanabilir denetime odaklanır; yoksa hedefin kendisine.
 */

export const SKIP_TARGET_MAIN = "fusion-main";
export const SKIP_TARGET_COMPOSER = "fusion-composer";

const ODAKLANABILIR = 'textarea, input:not([type="hidden"]), button, [href], select, [tabindex]:not([tabindex="-1"])';

export function focusSkipTarget(id: string, root: ParentNode = document): boolean {
  const hedef = root.querySelector<HTMLElement>(`#${id}`);
  if (!hedef) return false;
  const denetim = hedef.querySelector<HTMLElement>(ODAKLANABILIR);
  (denetim ?? hedef).focus();
  return true;
}

export function SkipLinks({ composer = true }: { composer?: boolean }) {
  const { t } = useLanguage();
  const atla = (id: string) => (event: MouseEvent<HTMLAnchorElement>) => {
    if (focusSkipTarget(id)) event.preventDefault();
  };
  return (
    <nav aria-label="Hızlı atlama" className="skip-links">
      <a href={`#${SKIP_TARGET_MAIN}`} onClick={atla(SKIP_TARGET_MAIN)}>{t("atla.icerik")}</a>
      {composer && <a href={`#${SKIP_TARGET_COMPOSER}`} onClick={atla(SKIP_TARGET_COMPOSER)}>{t("atla.mesaj")}</a>}
    </nav>
  );
}
