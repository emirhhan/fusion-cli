import claudeMark from "./sources/claude.svg";
import codexLight from "./sources/codex-light.png";
import codexDark from "./sources/codex-dark.png";
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
  if (kind === "claude") return <span aria-hidden="true" className="source-icon" data-source="claude"><img src={claudeMark} width={size} height={size} alt="" /></span>;
  if (kind === "codex") return <span aria-hidden="true" className="source-icon" data-source="codex"><img className="source-icon__light" src={codexLight} width={size} height={size} alt="" /><img className="source-icon__dark" src={codexDark} width={size} height={size} alt="" /></span>;
  const path = "M12 4l3 3-1.4 2.2 4.7-1.1-2.4 4-3.9-1.4-3.9 1.4-2.4-4 4.7 1.1L9 7zM10 12h4v8h-4z";
  return (
    <span aria-hidden="true" className="source-icon" data-source={kind}>
      <svg fill="currentColor" height={size} viewBox="0 0 24 24" width={size} xmlns="http://www.w3.org/2000/svg">
        <path d={path} fillRule="evenodd" />
      </svg>
    </span>
  );
}
