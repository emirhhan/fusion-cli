import { useCallback, useEffect, useRef, useState } from "react";
import type { ProtocolClient } from "../protocol/client";
import type {
  HistorySearchMatch,
  HistorySessionRef,
  HistorySourceName,
  HistorySourceRef,
  HistoryTurn,
} from "./types";

const PAGE_SIZE = 30;

/**
 * Arama neden sunucuda?
 *
 * Seçicinin elindeki liste kaynağın tamamı değil, indirilmiş sayfalarıdır; yerel
 * filtre eski bir konuşmayı hiçbir zaman göremez. Üstelik Claude oturumlarının
 * çoğunda başlık kaydı yoktur ve başlık tarih/boyut yedeğine düşer — başlığa
 * bakan bir arama pratikte hiçbir şey bulamaz. Bu yüzden sorgu çekirdeğe gider.
 */

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
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<HistorySearchMatch[]>([]);
  const [searchPartial, setSearchPartial] = useState(false);
  const [searchNotice, setSearchNotice] = useState("");
  const [searching, setSearching] = useState(false);
  // Son istek kazanır: her eşzamansız akışın nesil sayacı vardır; yanıt geldiğinde sayaç
  // değişmişse (kaynak/konuşma/sorgu değişti) sonuç yazılmaz.
  const sessionsGeneration = useRef(0);
  const turnsGeneration = useRef(0);
  const searchGeneration = useRef(0);

  const resetSearch = useCallback(() => {
    searchGeneration.current += 1;
    setSearchQuery("");
    setSearchResults([]);
    setSearchPartial(false);
    setSearchNotice("");
    setSearching(false);
  }, []);

  useEffect(() => {
    let active = true;
    // Sekmeye özgü seçim durumu (açık kaynak, seçili konuşma, dökümler…)
    // her istemci değişiminde sıfırlanır — farklı bir sekmeye geçildiğinde
    // önceki sekmenin gezinmesi taşınmamalı.
    //
    // AMA `sources` BURADA sıfırlanmıyor: Claude/Codex/Hermes geçmişi
    // diskten okunan GLOBAL bir listedir, aktif sekmeye özgü değildir.
    // Eskiden her sekme değişiminde `[]`'a düşürülüyordu; yeni sekmenin
    // çekirdeği henüz `gecmis.kaynaklar` isteğine cevap verecek kadar hazır
    // değilse (ya da istek herhangi bir sebeple başarısız olursa) kenar
    // çubuğundaki "Devam et" bölümü BİR DAHA HİÇ dolmuyordu — yalnız
    // uygulama yeniden başlayınca (taze istemciler) düzeliyordu. Liste artık
    // yeni bir istek BAŞARIYLA dönene kadar olduğu gibi kalır.
    sessionsGeneration.current += 1;
    turnsGeneration.current += 1;
    setSource(null);
    setSessions([]);
    setSessionCursor(null);
    setSelected(null);
    setTurns([]);
    setTurnCursor(null);
    setError(null);
    setLoading(false);
    resetSearch();
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
        // İstek başarısız olsa bile ÖNCEKİ kaynak listesi SİLİNMEZ (yukarıya
        // bkz.) — yalnız hata bildirilir.
        if (active) setError(String(reason));
      });
    return () => {
      active = false;
    };
  }, [client, resetSearch]);

  const searchSessions = useCallback(
    async (query: string) => {
      const trimmed = query.trim();
      if (!client || !source) return;
      if (!trimmed) {
        resetSearch();
        return;
      }
      const generation = ++searchGeneration.current;
      setSearchQuery(trimmed);
      setSearching(true);
      setError(null);
      try {
        const result = await client.request("gecmis.ara", { kaynak: source, sorgu: trimmed });
        if (generation !== searchGeneration.current) return;
        if (result.ok !== true || !Array.isArray(result.oturumlar)) {
          throw new Error(messageFrom(result, "Konuşmalarda arama yapılamadı."));
        }
        setSearchResults(result.oturumlar as HistorySearchMatch[]);
        setSearchPartial(result.kismi === true);
        setSearchNotice(typeof result.metin === "string" ? result.metin : "");
      } catch (reason) {
        if (generation !== searchGeneration.current) return;
        setSearchResults([]);
        setSearchPartial(false);
        setSearchNotice("");
        setError(String(reason));
      } finally {
        if (generation === searchGeneration.current) setSearching(false);
      }
    },
    [client, resetSearch, source],
  );

  const openSource = useCallback(
    async (name: HistorySourceName) => {
      if (!client) return;
      const generation = ++sessionsGeneration.current;
      turnsGeneration.current += 1;
      setLoading(true);
      setError(null);
      setSource(name);
      setSessions([]);
      setSessionCursor(null);
      setSelected(null);
      setTurns([]);
      setTurnCursor(null);
      resetSearch();
      try {
        const result = await client.request("gecmis.oturumlar", {
          kaynak: name,
          cursor: 0,
          limit: PAGE_SIZE,
        });
        if (generation !== sessionsGeneration.current) return;
        if (result.ok !== true || !Array.isArray(result.oturumlar)) {
          throw new Error(messageFrom(result, "Geçmiş konuşmalar alınamadı."));
        }
        setSessions(result.oturumlar as HistorySessionRef[]);
        setSessionCursor(typeof result.next_cursor === "number" ? result.next_cursor : null);
      } catch (reason) {
        if (generation === sessionsGeneration.current) setError(String(reason));
      } finally {
        if (generation === sessionsGeneration.current) setLoading(false);
      }
    },
    [client, resetSearch],
  );

  const loadMoreSessions = useCallback(async () => {
    if (!client || !source || sessionCursor === null || loading) return;
    const generation = sessionsGeneration.current;
    setLoading(true);
    setError(null);
    try {
      const result = await client.request("gecmis.oturumlar", {
        kaynak: source,
        cursor: sessionCursor,
        limit: PAGE_SIZE,
      });
      if (generation !== sessionsGeneration.current) return;
      if (result.ok !== true || !Array.isArray(result.oturumlar)) {
        throw new Error(messageFrom(result, "Daha fazla konuşma alınamadı."));
      }
      setSessions((current) => [...current, ...(result.oturumlar as HistorySessionRef[])]);
      setSessionCursor(typeof result.next_cursor === "number" ? result.next_cursor : null);
    } catch (reason) {
      if (generation === sessionsGeneration.current) setError(String(reason));
    } finally {
      if (generation === sessionsGeneration.current) setLoading(false);
    }
  }, [client, loading, sessionCursor, source]);

  const selectSession = useCallback(
    async (session: HistorySessionRef) => {
      if (!client) return;
      const generation = ++turnsGeneration.current;
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
        if (generation !== turnsGeneration.current) return;
        if (result.ok !== true || !Array.isArray(result.turlar)) {
          throw new Error(messageFrom(result, "Konuşma önizlemesi alınamadı."));
        }
        setTurns(result.turlar as HistoryTurn[]);
        setTurnCursor(typeof result.next_cursor === "number" ? result.next_cursor : null);
      } catch (reason) {
        if (generation === turnsGeneration.current) setError(String(reason));
      } finally {
        if (generation === turnsGeneration.current) setLoading(false);
      }
    },
    [client],
  );

  const loadMoreTurns = useCallback(async () => {
    if (!client || !selected || turnCursor === null || loading) return;
    const generation = turnsGeneration.current;
    setLoading(true);
    setError(null);
    try {
      const result = await client.request("gecmis.onizle", {
        kaynak: selected.kaynak,
        oturum_id: selected.oturum_id,
        cursor: turnCursor,
        limit: PAGE_SIZE,
      });
      if (generation !== turnsGeneration.current) return;
      if (result.ok !== true || !Array.isArray(result.turlar)) {
        throw new Error(messageFrom(result, "Önizlemenin devamı alınamadı."));
      }
      setTurns((current) => [...current, ...(result.turlar as HistoryTurn[])]);
      setTurnCursor(typeof result.next_cursor === "number" ? result.next_cursor : null);
    } catch (reason) {
      if (generation === turnsGeneration.current) setError(String(reason));
    } finally {
      if (generation === turnsGeneration.current) setLoading(false);
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
    searchNotice,
    searchPartial,
    searchQuery,
    searchResults,
    searchSessions,
    searching,
    turnCursor,
    turns,
  };
}

export type HistoryController = ReturnType<typeof useHistory>;
