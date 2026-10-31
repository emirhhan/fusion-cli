import { useEffect, useRef, useState } from "react";
import type { ProtocolClient } from "../protocol/client";
import "./LinkedPullRequest.css";

/**
 * Oturumun bağlı olduğu PR rozeti (P-057) — Claude Code'un PR'a bağlı oturum göstergesinin
 * karşılığı. Turda `gh pr create` ile açılan (ya da `gh pr view` ile okunan) PR çekirdekte
 * oturum künyesi olur (`oturum.durum.pr`); şerit tur bitince yeniden okunur ve tıklanınca PR
 * tarayıcıda açılır. Bağlı PR yoksa hiçbir şey çizilmez.
 */

export interface LinkedPr {
  numara: number;
  url: string;
  depo: string;
}

export function prFrom(raw: unknown): LinkedPr | null {
  if (!raw || typeof raw !== "object") return null;
  const value = raw as Record<string, unknown>;
  if (typeof value.numara !== "number" || typeof value.url !== "string" || !/^https:\/\//.test(value.url)) return null;
  return { numara: value.numara, url: value.url, depo: typeof value.depo === "string" ? value.depo : "" };
}

async function openExternal(url: string): Promise<void> {
  const { openUrl } = await import("@tauri-apps/plugin-opener");
  await openUrl(url);
}

interface LinkedPullRequestProps {
  client: ProtocolClient | undefined;
  /** Tur sürüyor mu? Tur bitince (true → false) künye yeniden okunur. */
  running?: boolean;
  /** Test için: dış bağlantı açıcı. */
  open?: (url: string) => Promise<void>;
}

export function LinkedPullRequest({ client, running = false, open = openExternal }: LinkedPullRequestProps) {
  const [pr, setPr] = useState<LinkedPr | null>(null);
  const owner = useRef(0);

  useEffect(() => {
    if (!client || running) return;
    const generation = ++owner.current;
    client.request("oturum.durum", {}).then((payload) => {
      if (generation === owner.current) setPr(prFrom((payload as Record<string, unknown>)?.pr));
    }).catch(() => { /* künye okunamazsa rozet çizilmez; sohbet çalışır */ });
  }, [client, running]);

  if (!pr) return null;
  return (
    <div className="linked-pr-kolon">
      <button
        className="linked-pr"
        type="button"
        title={pr.url}
        aria-label={`Bağlı PR #${pr.numara}${pr.depo ? ` (${pr.depo})` : ""} — tarayıcıda aç`}
        onClick={() => { void open(pr.url).catch(() => undefined); }}
      >
        <span className="linked-pr__etiket">PR #{pr.numara}</span>
        {pr.depo && <span className="linked-pr__depo">{pr.depo}</span>}
      </button>
    </div>
  );
}
