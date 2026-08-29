import type { ReactNode, SVGProps } from "react";

export type IconName =
  | "attach"
  | "changes"
  | "chevron"
  | "files"
  | "lessons"
  | "new"
  | "panel"
  | "preview"
  | "search"
  | "send"
  | "settings"
  | "sidebar"
  | "skills"
  | "terminal"
  | "tests";

const paths: Record<IconName, ReactNode> = {
  attach: <path d="m20.5 11.5-8.9 8.9a5 5 0 0 1-7.1-7.1l9.6-9.6a3.5 3.5 0 0 1 5 5l-9.6 9.6a2 2 0 0 1-2.8-2.8l8.9-8.9" />,
  changes: <><path d="M5 7h10" /><path d="m12 4 3 3-3 3" /><path d="M19 17H9" /><path d="m12 14-3 3 3 3" /></>,
  chevron: <path d="m9 18 6-6-6-6" />,
  files: <><path d="M6 3h8l4 4v14H6z" /><path d="M14 3v5h4" /></>,
  lessons: <><path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H11v17H6.5A2.5 2.5 0 0 0 4 22.5z" /><path d="M20 5.5A2.5 2.5 0 0 0 17.5 3H13v17h4.5a2.5 2.5 0 0 1 2.5 2.5z" /></>,
  new: <><path d="M12 5v14" /><path d="M5 12h14" /></>,
  panel: <><rect width="18" height="16" x="3" y="4" rx="2" /><path d="M15 4v16" /></>,
  preview: <><path d="M2.5 12s3.5-6 9.5-6 9.5 6 9.5 6-3.5 6-9.5 6-9.5-6-9.5-6" /><circle cx="12" cy="12" r="2.5" /></>,
  search: <><circle cx="11" cy="11" r="7" /><path d="m20 20-4-4" /></>,
  send: <><path d="m22 2-7 20-4-9-9-4z" /><path d="M22 2 11 13" /></>,
  settings: <><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-2.8 2.8-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.6v.2h-4V21a1.7 1.7 0 0 0-1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1L4.2 17l.1-.1a1.7 1.7 0 0 0 .3-1.9A1.7 1.7 0 0 0 3 14H2.8v-4H3a1.7 1.7 0 0 0 1.6-1 1.7 1.7 0 0 0-.3-1.9L4.2 7 7 4.2l.1.1a1.7 1.7 0 0 0 1.9.3A1.7 1.7 0 0 0 10 3V2.8h4V3a1.7 1.7 0 0 0 1 1.6 1.7 1.7 0 0 0 1.9-.3l.1-.1L19.8 7l-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.6 1h.2v4H21a1.7 1.7 0 0 0-1.6 1Z" /></>,
  sidebar: <><rect width="18" height="16" x="3" y="4" rx="2" /><path d="M9 4v16" /></>,
  skills: <><path d="m12 3 1.4 4.2L18 8.5l-3.5 2.7.1 4.5-3.6-2.5-3.6 2.5.1-4.5L4 8.5l4.6-1.3z" /><path d="M17 17v4" /><path d="M15 19h4" /></>,
  terminal: <><path d="m5 7 4 4-4 4" /><path d="M11 17h8" /></>,
  tests: <><path d="M9 3h6" /><path d="M10 3v5l-5 9a2.5 2.5 0 0 0 2.2 4h9.6a2.5 2.5 0 0 0 2.2-4l-5-9V3" /><path d="M8 15h8" /></>,
};

interface IconProps extends Omit<SVGProps<SVGSVGElement>, "name"> {
  name: IconName;
  size?: number;
  title?: string;
}

export function Icon({ name, size = 20, title, ...props }: IconProps) {
  return (
    <svg
      aria-hidden={title ? undefined : true}
      aria-label={title}
      fill="none"
      height={size}
      role={title ? "img" : undefined}
      stroke="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth="1.75"
      viewBox="0 0 24 24"
      width={size}
      {...props}
    >
      {title && <title>{title}</title>}
      {paths[name]}
    </svg>
  );
}
