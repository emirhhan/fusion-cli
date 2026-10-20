import React, { useState } from "react";
import { createRoot } from "react-dom/client";
import { Sidebar } from "../src/screens/Sidebar";
import { useProjectRegistry } from "../src/sessions/useProjectRegistry";
import "../src/theme/tokens.css";
import "../src/brand/fonts.css";
document.documentElement.dataset.theme = new URLSearchParams(location.search).get("theme") ?? "light";

let sayac = 0;
const yeniKimlik = () => `p${++sayac}-${Date.now()}`;

function Preview() {
  const projects = useProjectRegistry(yeniKimlik);
  const [sohbetler, setSohbetler] = useState([
    { session_id: "c1", source: "fusion", title: "Sepet hatası", project: "Desktop", projectRoot: "/Users/t/Desktop" },
    { session_id: "c2", source: "fusion", title: "Fiyat tablosu", project: "Desktop", projectRoot: "/Users/t/Desktop" },
  ]);
  let alici = 2;
  return <div style={{ height: "100dvh", width: 280 }}><Sidebar
    etkin={null}
    onSec={() => undefined}
    onYeni={() => setSohbetler((l) => [{ session_id: `c${++alici + l.length}`, source: "fusion", title: "Yeni sohbet", project: "Desktop", projectRoot: "/Users/t/Desktop" }, ...l])}
    onNavigate={(hedef) => {
      const id = hedef.replace("project-id:", "");
      if (hedef.startsWith("project-id:")) {
        const sid = `n${Date.now()}`;
        projects.assign(sid, id);
        setSohbetler((l) => [{ session_id: sid, source: "fusion", title: "Projede yeni sohbet", project: "Desktop", projectRoot: "/Users/t/Desktop" }, ...l]);
      }
    }}
    onProjectCreate={(girdi) => { projects.create(girdi); }}
    onProjectRename={projects.rename}
    onProjectDelete={projects.remove}
    onAssign={projects.assign}
    onPickFolder={async () => "/Users/t/blog"}
    onSil={(id) => { setSohbetler((l) => l.filter((s) => s.session_id !== id)); projects.forget(id); }}
    oturumlar={sohbetler.map((s) => ({ ...s, projectId: projects.registry.chats[s.session_id] }))}
    projeler={projects.registry.projects.map((r) => ({ id: r.id, name: r.name, pinned: false, root: r.root ?? "", updated_at: r.createdAt }))}
  /></div>;
}
createRoot(document.getElementById("root")!).render(<Preview />);
