import type { ReactNode } from "react";
import "./StatusRow.css";

type StatusTone = "neutral" | "success" | "warning" | "danger";

interface StatusRowProps {
  action?: ReactNode;
  description?: string;
  label: string;
  status: string;
  tone?: StatusTone;
}

export function StatusRow({
  action,
  description,
  label,
  status,
  tone = "neutral",
}: StatusRowProps) {
  return (
    <div className="status-row">
      <div className="status-row__identity">
        <strong>{label}</strong>
        {description && <span>{description}</span>}
      </div>
      <div className="status-row__end">
        <span className="status-row__status" data-tone={tone}>
          <span aria-hidden="true" />
          {status}
        </span>
        {action}
      </div>
    </div>
  );
}
