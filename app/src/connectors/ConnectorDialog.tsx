import { useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { useModalFocus } from "../ui/useModalFocus";

export function ConnectorDialog({ children, label, onClose }: { children: ReactNode; label: string; onClose: () => void }) {
  const ref = useRef<HTMLDivElement>(null);
  useModalFocus(ref, true, onClose);
  return createPortal(<div className="connector-dialog__backdrop"><div aria-label={label} aria-modal="true" className="connector-dialog" ref={ref} role="dialog" tabIndex={-1}>{children}</div></div>, document.body);
}
