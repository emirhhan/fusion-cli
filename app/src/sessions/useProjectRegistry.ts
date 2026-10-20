import { useCallback, useRef, useState } from "react";
import {
  addProject, assignChat, emptyRegistry, forgetChat, loadRegistry, removeProject, renameProject, saveRegistry,
  type ProjectRegistry,
} from "./projectRecords";

const browserStorage = () => window.localStorage;

/** Kalıcı proje kaydı durumu; her başarılı değişiklik hemen depolamaya yazılır. */
export function useProjectRegistry(newId: () => string) {
  const [registry, setRegistry] = useState<ProjectRegistry>(() =>
    typeof window === "undefined" ? emptyRegistry : loadRegistry(browserStorage));
  const latest = useRef(registry);

  /** Doğrulama hatası fırlatır ve durumu değiştirmez; arayüz mesajı gösterir. */
  const commit = useCallback((change: (current: ProjectRegistry) => ProjectRegistry) => {
    const next = change(latest.current);
    latest.current = next;
    saveRegistry(browserStorage, next);
    setRegistry(next);
  }, []);

  const create = useCallback((input: { name: string; root?: string }): string => {
    const id = newId();
    commit((current) => addProject(current, { id, name: input.name, root: input.root, now: Date.now() }));
    return id;
  }, [commit, newId]);
  const rename = useCallback((id: string, name: string) => commit((current) => renameProject(current, id, name)), [commit]);
  const remove = useCallback((id: string) => commit((current) => removeProject(current, id)), [commit]);
  const assign = useCallback((chatId: string, projectId: string | null) => commit((current) => assignChat(current, chatId, projectId)), [commit]);
  const forget = useCallback((chatId: string) => commit((current) => forgetChat(current, chatId)), [commit]);

  return { registry, create, rename, remove, assign, forget };
}
