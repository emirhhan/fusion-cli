import type { AjanKarti } from "../team/ekipOlaylari";
import { Icon } from "../ui/Icon";
import { ToolTrail } from "./ActivityLine";

/** Ekip kartlarının ayrıntısı panelde kalır; sohbet kronolojide kısa bir iz taşır. */
export function AgentActivity({ agents, running }: { agents: AjanKarti[]; running: boolean }) {
  return <div className="agent-activity">
    {agents.map((agent) => {
      const state = agent.durum === "bitti" ? "çalışmayı bitirdi"
        : agent.durum === "calisiyor" ? (running ? "çalışıyor" : "çalışması duraklatıldı")
        : agent.durum === "iptal" ? "çalışması iptal edildi" : "çalışması yarım kaldı";
      return <details className="activity__summary" key={agent.id}>
        <summary><Icon name="sparkle" className="agent-activity__icon" /><span>{agent.unvan} {state}</span></summary>
        <div className="agent-activity__detail"><p>{agent.gorev}</p><ToolTrail adimlar={agent.adimlar} /></div>
      </details>;
    })}
  </div>;
}
