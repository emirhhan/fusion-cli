import { Logo } from "./Logo";
import "./SourceIcon.css";

type KnownSource = "fusion" | "claude" | "codex" | "hermes";

function knownSource(source: string): KnownSource {
  const normalized = source.toLocaleLowerCase("tr");
  return normalized === "claude" || normalized === "codex" || normalized === "hermes"
    ? normalized
    : "fusion";
}

export function SourceIcon({ source, size = 18 }: { source: string; size?: number }) {
  const kind = knownSource(source);
  if (kind === "fusion") {
    return <span aria-hidden="true" className="source-icon" data-source="fusion"><Logo size={size} /></span>;
  }
  const path = {
    claude: "M12 2.8l2.1 6.1 5.9-2.5-3.8 5.2 5.8 2.7-6.4.1 1.8 6.2-5.4-3.7-5.4 3.7 1.8-6.2-6.4-.1 5.8-2.7L4 6.4l5.9 2.5z",
    codex: "M12 3.2l4.8 2.7v5.4L12 14l-4.8-2.7V5.9zM7.2 11.3v5.4l4.8 2.7 4.8-2.7v-5.4L12 14z",
    hermes: "M12 4l3 3-1.4 2.2 4.7-1.1-2.4 4-3.9-1.4-3.9 1.4-2.4-4 4.7 1.1L9 7zM10 12h4v8h-4z",
  }[kind];
  return (
    <span aria-hidden="true" className="source-icon" data-source={kind}>
      <svg fill="currentColor" height={size} viewBox="0 0 24 24" width={size} xmlns="http://www.w3.org/2000/svg">
        <path d={path} fillRule="evenodd" />
      </svg>
    </span>
  );
}
