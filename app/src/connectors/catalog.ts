/** Bilinen MCP sunucularının küratörlü kataloğu.
 *
 * Amaç: kullanıcı en çok kullanılan sunuculara komut/URL ezberlemeden tek tıkla
 * bağlansın. Her giriş `baglanti.ekle` RPC'sinin BEKLEDİĞİ alanları taşır; ekran
 * yalnız bunu iletir, kendi uç noktasını uydurmaz.
 *
 * Uç noktalar ve paketler sağlayıcıların yayımladığı belgelerden derlendi.
 * Değişebilirler; katalog bir BAŞLANGIÇ değeridir, kullanıcı "Ekle" ile kendi
 * değerini girip düzeltebilir.
 * Remote uç noktalar backend'de `validate_remote_mcp_url`'den geçer: HTTPS
 * zorunlu, düz HTTP yalnız loopback (Figma masaüstü) için.
 */

export type ConnectorTransport = "stdio" | "streamable_http";
export type SetupFieldTarget = "argument" | "environment" | "secret_argument";

export interface SetupField {
  id: string;
  label: string;
  placeholder: string;
  secret?: boolean;
  target: SetupFieldTarget;
  environmentName?: string;
}

export interface CatalogEntry {
  /** Bağlantının kaydedileceği ad (baglanti.ekle `ad`). Benzersiz. */
  id: string;
  /** Ekranda görünen etiket. */
  label: string;
  /** Bir cümlelik ne-işe-yarar. */
  description: string;
  /** Gruplama ve tint için kategori. */
  category: "Ticaret" | "Geliştirme" | "Üretkenlik" | "Veri" | "Araç";
  /** İkon kutusunun rengi (kategori kimliği; marka rengini taklit etmez). */
  tint: string;
  /** İkon monogramı (1-2 harf). */
  glyph: string;
  transport: ConnectorTransport;
  /** stdio için çalıştırılacak komut (shlex ile parçalanır). */
  command?: string;
  /** streamable_http için MCP adresi. */
  url?: string;
  /** OAuth kapsamları (boşlukla ayrılmış). Çoğu remote sunucu boş kabul eder. */
  scopes?: string;
  /** Üstte öne çıkan banner kartı mı? Tam 3 giriş işaretli. */
  featured?: boolean;
  /** Bağlanınca OAuth girişi gerektirir mi? (Sadece bilgilendirme rozeti.) */
  oauth?: boolean;
  /** Bağlantı kurulmadan önce kullanıcıdan alınması gereken alanlar. */
  setup?: readonly SetupField[];
}

const CATALOG: readonly CatalogEntry[] = [
  // --- Banner (öne çıkan 3) ------------------------------------------------ //
  {
    id: "shopify",
    label: "Shopify",
    description: "Mağaza geliştirme dokümanları ve GraphQL şeması araçları.",
    category: "Ticaret",
    tint: "#5a8f3d",
    glyph: "Sh",
    transport: "stdio",
    command: "npx -y @shopify/dev-mcp@latest",
    featured: true,
  },
  {
    id: "github",
    label: "GitHub",
    description: "Depo, konu, pull request ve kod araması; resmi uzak MCP.",
    category: "Geliştirme",
    tint: "#6e7681",
    glyph: "GH",
    transport: "streamable_http",
    url: "https://api.githubcopilot.com/mcp/",
    oauth: true,
    featured: true,
  },
  {
    id: "google-drive",
    label: "Google Drive",
    description: "Dosya arama ve içerik okuma; Google hesabıyla yetkilendirilir.",
    category: "Üretkenlik",
    tint: "#3b7ddd",
    glyph: "GD",
    transport: "stdio",
    command: "npx -y @modelcontextprotocol/server-gdrive",
    oauth: true,
    featured: true,
  },

  // --- Katalog ------------------------------------------------------------- //
  {
    id: "notion",
    label: "Notion",
    description: "Sayfa, veritabanı ve içerik araçları; resmi uzak MCP.",
    category: "Üretkenlik",
    tint: "#8a8a86",
    glyph: "No",
    transport: "streamable_http",
    url: "https://mcp.notion.com/sse",
    oauth: true,
  },
  {
    id: "linear",
    label: "Linear",
    description: "Konu, proje ve döngü yönetimi; resmi uzak MCP.",
    category: "Geliştirme",
    tint: "#5b60d6",
    glyph: "Li",
    transport: "streamable_http",
    url: "https://mcp.linear.app/sse",
    oauth: true,
  },
  {
    id: "sentry",
    label: "Sentry",
    description: "Hata izleme ve olay ayrıntıları; resmi uzak MCP.",
    category: "Geliştirme",
    tint: "#8b5cf6",
    glyph: "Se",
    transport: "streamable_http",
    url: "https://mcp.sentry.dev/sse",
    oauth: true,
  },
  {
    id: "stripe",
    label: "Stripe",
    description: "Ödeme, müşteri ve fatura araçları; resmi uzak MCP.",
    category: "Ticaret",
    tint: "#635bff",
    glyph: "St",
    transport: "streamable_http",
    url: "https://mcp.stripe.com/",
    oauth: true,
  },
  {
    id: "atlassian",
    label: "Atlassian",
    description: "Jira ve Confluence araçları; resmi uzak MCP.",
    category: "Üretkenlik",
    tint: "#2b7fff",
    glyph: "At",
    transport: "streamable_http",
    url: "https://mcp.atlassian.com/v1/sse",
    oauth: true,
  },
  {
    id: "cloudflare",
    label: "Cloudflare",
    description: "Workers, bağlamalar ve gözlemlenebilirlik; resmi uzak MCP.",
    category: "Geliştirme",
    tint: "#f38020",
    glyph: "Cf",
    transport: "streamable_http",
    url: "https://bindings.mcp.cloudflare.com/sse",
    oauth: true,
  },
  {
    id: "asana",
    label: "Asana",
    description: "Görev ve proje yönetimi; resmi uzak MCP.",
    category: "Üretkenlik",
    tint: "#f06a6a",
    glyph: "As",
    transport: "streamable_http",
    url: "https://mcp.asana.com/sse",
    oauth: true,
  },
  {
    id: "vercel",
    label: "Vercel",
    description: "Dağıtım ve proje araçları; resmi uzak MCP.",
    category: "Geliştirme",
    tint: "#8b8b8b",
    glyph: "Ve",
    transport: "streamable_http",
    url: "https://mcp.vercel.com",
    oauth: true,
  },
  {
    id: "slack",
    label: "Slack",
    description: "Kanal ve mesaj araçları; bot jetonu ile çalışır.",
    category: "Üretkenlik",
    tint: "#4a154b",
    glyph: "Sl",
    transport: "stdio",
    command: "npx -y @modelcontextprotocol/server-slack",
    setup: [
      {
        id: "bot-token",
        label: "Slack bot jetonu",
        placeholder: "xoxb-…",
        secret: true,
        target: "environment",
        environmentName: "SLACK_BOT_TOKEN",
      },
      {
        id: "team-id",
        label: "Slack çalışma alanı kimliği",
        placeholder: "T01234567",
        target: "environment",
        environmentName: "SLACK_TEAM_ID",
      },
    ],
  },
  {
    id: "gmail",
    label: "Gmail",
    description: "E-posta okuma ve gönderme; Google hesabıyla yetkilendirilir.",
    category: "Üretkenlik",
    tint: "#d64b3f",
    glyph: "Gm",
    transport: "stdio",
    command: "npx -y @modelcontextprotocol/server-gmail",
    oauth: true,
  },
  {
    id: "postgres",
    label: "PostgreSQL",
    description: "Salt-okunur sorgu ve şema inceleme.",
    category: "Veri",
    tint: "#336791",
    glyph: "Pg",
    transport: "stdio",
    command: "npx -y @modelcontextprotocol/server-postgres",
    setup: [
      {
        id: "dsn",
        label: "PostgreSQL bağlantı adresi",
        placeholder: "postgresql://kullanici:parola@localhost/veritabani",
        secret: true,
        target: "secret_argument",
        environmentName: "POSTGRES_URL",
      },
    ],
  },
  {
    id: "filesystem",
    label: "Dosya sistemi",
    description: "Belirli bir klasörde güvenli dosya okuma ve yazma.",
    category: "Araç",
    tint: "#6b7280",
    glyph: "Fs",
    transport: "stdio",
    command: "npx -y @modelcontextprotocol/server-filesystem",
    setup: [
      {
        id: "root",
        label: "İzin verilen klasör",
        placeholder: "/Users/ad/Proje",
        target: "argument",
      },
    ],
  },
  {
    id: "brave-search",
    label: "Brave Search",
    description: "Web araması; Brave API anahtarı ister.",
    category: "Araç",
    tint: "#fb542b",
    glyph: "Br",
    transport: "stdio",
    command: "npx -y @modelcontextprotocol/server-brave-search",
    setup: [
      {
        id: "api-key",
        label: "Brave API anahtarı",
        placeholder: "BSA…",
        secret: true,
        target: "environment",
        environmentName: "BRAVE_API_KEY",
      },
    ],
  },
  {
    id: "puppeteer",
    label: "Puppeteer",
    description: "Başsız tarayıcı ile sayfa gezme ve ekran görüntüsü.",
    category: "Araç",
    tint: "#40b5a4",
    glyph: "Pp",
    transport: "stdio",
    command: "npx -y @modelcontextprotocol/server-puppeteer",
  },
  {
    id: "fetch",
    label: "Fetch",
    description: "URL getirme ve içeriği metne çevirme.",
    category: "Araç",
    tint: "#0ea5e9",
    glyph: "Ft",
    transport: "stdio",
    command: "uvx mcp-server-fetch",
  },
  {
    id: "sequential-thinking",
    label: "Sıralı Düşünme",
    description: "Adım adım muhakeme için yardımcı düşünme aracı.",
    category: "Araç",
    tint: "#10b981",
    glyph: "Sq",
    transport: "stdio",
    command: "npx -y @modelcontextprotocol/server-sequential-thinking",
  },
  {
    id: "figma",
    label: "Figma",
    description: "Tasarım dosyası ve düğüm bağlamı; Figma masaüstü geliştirme modu.",
    category: "Araç",
    tint: "#a259ff",
    glyph: "Fi",
    transport: "streamable_http",
    url: "http://127.0.0.1:3845/sse",
  },
];

/** Öne çıkan banner girişleri (tam 3). */
export const featuredConnectors: readonly CatalogEntry[] = CATALOG.filter((e) => e.featured);

/** Banner dışında kalan katalog girişleri. */
export const catalogConnectors: readonly CatalogEntry[] = CATALOG.filter((e) => !e.featured);

/** Tüm katalog. */
export const allConnectors: readonly CatalogEntry[] = CATALOG;

/** Bir katalog girişini `baglanti.ekle` RPC yüküne çevir. */
export function addPayloadFor(
  entry: CatalogEntry,
  values: Readonly<Record<string, string>> = {},
): Record<string, unknown> {
  if (entry.transport === "stdio") {
    const arguments_ = entry.setup
      ?.filter((field) => field.target === "argument" || field.target === "secret_argument")
      .map((field) =>
        field.target === "secret_argument"
          ? `__FUSION_SECRET__:${field.environmentName}`
          : values[field.id],
      )
      .filter(Boolean);
    const environment = Object.fromEntries(
      (entry.setup ?? [])
        .filter(
          (field) =>
            (field.target === "environment" || field.target === "secret_argument") &&
            field.environmentName,
        )
        .map((field) => [field.environmentName!, values[field.id]]),
    );
    return {
      ad: entry.id,
      komut: entry.command,
      ...(arguments_?.length ? { argumanlar: arguments_ } : {}),
      ...(Object.keys(environment).length ? { ortam: environment } : {}),
    };
  }
  return {
    ad: entry.id,
    tasima: entry.transport,
    url: entry.url,
    kapsamlar: entry.scopes ?? "",
    client_id: "",
  };
}
