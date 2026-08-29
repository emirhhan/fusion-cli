import type { ButtonHTMLAttributes, ReactNode } from "react";
import { Icon, type IconName } from "./Icon";
import "./controls.css";

type ButtonVariant = "primary" | "secondary" | "ghost" | "danger" | "icon";

interface CommonButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  icon?: IconName;
  loading?: boolean;
  variant?: ButtonVariant;
}

type ButtonProps = CommonButtonProps &
  (
    | { iconOnly: true; "aria-label": string; children?: never }
    | { iconOnly?: false; children: ReactNode }
  );

export function Button({
  children,
  className = "",
  disabled,
  icon,
  iconOnly = false,
  loading = false,
  type = "button",
  variant = iconOnly ? "icon" : "secondary",
  ...props
}: ButtonProps) {
  const classes = ["ui-button", `ui-button--${variant}`, iconOnly ? "ui-button--icon-only" : "", className]
    .filter(Boolean)
    .join(" ");

  return (
    <button
      aria-busy={loading || undefined}
      className={classes}
      disabled={disabled || loading}
      type={type}
      {...props}
    >
      {icon && <Icon name={icon} size={18} />}
      {children && <span className="ui-button__label">{children}</span>}
      {loading && <span className="ui-button__status">Yükleniyor</span>}
    </button>
  );
}
