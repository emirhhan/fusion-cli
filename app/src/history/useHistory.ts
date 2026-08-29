import { useCallback, useEffect, useState } from "react";
import type { ProtocolClient } from "../protocol/client";
import type {
  HistorySessionRef,
  HistorySourceName,
  HistorySourceRef,
  HistoryTurn,
} from "./types";

const PAGE_SIZE = 30;

function messageFrom(result: Record<string, unknown>, fallback: string): string {
  return typeof result.metin === "string" ? result.metin : fallback;
}

export function useHistory(client: ProtocolClient | null) {
  const [sources, setSources] = useState<HistorySourceRef[]>([]);
  const [source, setSource] = useState<HistorySourceName | null>(null);
  const [sessions, setSessions] = useState<HistorySessionRef[]>([]);
  const [sessionCursor, setSessionCursor] = useState<number | null>(null);
  const [selected, setSelected] = useState<HistorySessionRef | null>(null);
  const [turns, setTurns] = useState<HistoryTurn[]>([]);
  const [turnCursor, setTurnCursor] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setSources([]);
    setSource(null);
    setSessions([]);
    setSessionCursor(null);
    setSelected(null);
    setTurns([]);
    setTurnCursor(null);
    setError(null);
    setLoading(false);
    if (!client) return;
    void client
      .request("gecmis.kaynaklar", {})
      .then((result) => {
        if (!active) return;
        if (result.ok !== true || !Array.isArray(result.kaynaklar)) {
          throw new Error(messageFrom(result, "Geçmiş kaynakları alınamadı."));
        }
        setSources(result.kaynaklar as HistorySourceRef[]);
      })
      .catch((reason) => {
        if (active) setError(String(reason));
      });
    return () => {
      active = false;
    };
  }, [client]);

  const openSource = useCallback(
    async (name: HistorySourceName) => {
      if (!client) return;
      setLoading(true);
      setError(null);
      setSource(name);
      setSessions([]);
      setSessionCursor(null);
      setSelected(null);
      setTurns([]);
      setTurnCursor(null);
      try {
        const result = await client.request("gecmis.oturumlar", {
          kaynak: name,
          cursor: 0,
          limit: PAGE_SIZE,
        });
        if (result.ok !== true || !Array.isArray(result.oturumlar)) {
          throw new Error(messageFrom(result, "Geçmiş konuşmalar alınamadı."));
        }
        setSessions(result.oturumlar as HistorySessionRef[]);
        setSessionCursor(typeof result.next_cursor === "number" ? result.next_cursor : null);
      } catch (reason) {
        setError(String(reason));
      } finally {
        setLoading(false);
      }
    },
    [client],
  );

  const loadMoreSessions = useCallback(async () => {
    if (!client || !source || sessionCursor === null || loading) return;
    setLoading(true);
    setError(null);
    try {
      const result = await client.request("gecmis.oturumlar", {
        kaynak: source,
        cursor: sessionCursor,
        limit: PAGE_SIZE,
      });
      if (result.ok !== true || !Array.isArray(result.oturumlar)) {
        throw new Error(messageFrom(result, "Daha fazla konuşma alınamadı."));
      }
      setSessions((current) => [...current, ...(result.oturumlar as HistorySessionRef[])]);
      setSessionCursor(typeof result.next_cursor === "number" ? result.next_cursor : null);
    } catch (reason) {
      setError(String(reason));
    } finally {
      setLoading(false);
    }
  }, [client, loading, sessionCursor, source]);

  const selectSession = useCallback(
    async (session: HistorySessionRef) => {
      if (!client) return;
      setLoading(true);
      setError(null);
      setSelected(session);
      setTurns([]);
      setTurnCursor(null);
      try {
        const result = await client.request("gecmis.onizle", {
          kaynak: session.kaynak,
          oturum_id: session.oturum_id,
          cursor: 0,
          limit: PAGE_SIZE,
        });
        if (result.ok !== true || !Array.isArray(result.turlar)) {
          throw new Error(messageFrom(result, "Konuşma önizlemesi alınamadı."));
        }
        setTurns(result.turlar as HistoryTurn[]);
        setTurnCursor(typeof result.next_cursor === "number" ? result.next_cursor : null);
      } catch (reason) {
        setError(String(reason));
      } finally {
        setLoading(false);
      }
    },
    [client],
  );

  const loadMoreTurns = useCallback(async () => {
    if (!client || !selected || turnCursor === null || loading) return;
    setLoading(true);
    setError(null);
    try {
      const result = await client.request("gecmis.onizle", {
        kaynak: selected.kaynak,
        oturum_id: selected.oturum_id,
        cursor: turnCursor,
        limit: PAGE_SIZE,
      });
      if (result.ok !== true || !Array.isArray(result.turlar)) {
        throw new Error(messageFrom(result, "Önizlemenin devamı alınamadı."));
      }
      setTurns((current) => [...current, ...(result.turlar as HistoryTurn[])]);
      setTurnCursor(typeof result.next_cursor === "number" ? result.next_cursor : null);
    } catch (reason) {
      setError(String(reason));
    } finally {
      setLoading(false);
    }
  }, [client, loading, selected, turnCursor]);

  return {
    error,
    loadMoreSessions,
    loadMoreTurns,
    loading,
    openSource,
    selected,
    selectSession,
    sessionCursor,
    sessions,
    source,
    sources,
    turnCursor,
    turns,
  };
}

export type HistoryController = ReturnType<typeof useHistory>;
