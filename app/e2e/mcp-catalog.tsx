import { useState } from 'react';
import { createRoot } from 'react-dom/client';
import '../src/theme/tokens.css';
import '../src/connectors/ConnectorsScreen.css';
import { McpToolCatalog } from '../src/connectors/McpToolCatalog';
import type { ProtocolClient } from '../src/protocol/client';
const client = { request: async () => ({ ok: true, schemaVersion: 1, total: 1, truncated: false, tools: [{ name: `server__${'long_name_'.repeat(20)}`, server: 'server', description: 'Sunucu tarafından sağlanan araç açıklaması.', effect: 'remote_write', parameters: [{ name: 'query', type: 'string', required: true, description: 'Arama metni' }], parametersTruncated: false }] }) } as unknown as ProtocolClient;
function Fixture() {
  const [open, setOpen] = useState(false);
  return <><button onClick={() => setOpen(true)}>Kataloğu aç</button>{open && <McpToolCatalog client={client} server='server' onClose={() => setOpen(false)} />}</>;
}
createRoot(document.getElementById('root')!).render(<Fixture />);
