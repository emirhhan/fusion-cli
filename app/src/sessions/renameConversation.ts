/** Sohbete kalıcı ad ver: CLI `/rename` ile aynı kayıt (`sohbet.adlandir`, #443). */
interface RenameClient {
  request: (name: string, data: Record<string, unknown>) => Promise<Record<string, unknown>>;
}

export async function renameConversation(client: RenameClient, id: string, name: string): Promise<string> {
  const ad = name.trim();
  if (!ad) throw new Error("Sohbet adı boş olamaz.");
  const result = await client.request("sohbet.adlandir", { sohbet_id: id, ad });
  if (result.ok !== true) throw new Error(String(result.metin ?? "Sohbet adlandırılamadı."));
  return typeof result.ad === "string" && result.ad.trim() ? result.ad.trim() : ad;
}
