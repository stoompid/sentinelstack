const API_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"
const API_KEY = process.env.NEXT_PUBLIC_API_KEY || ""

async function fetchJSON<T>(path: string, options?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options?.headers as Record<string, string>),
  }
  if (API_KEY) {
    headers["X-API-Key"] = API_KEY
  }
  const res = await fetch(`${API_URL}${path}`, {
    ...options,
    headers,
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`API ${res.status}: ${text}`)
  }
  return res.json()
}

export interface Article {
  article_id: string
  source: string
  title: string
  country: string | null
  categories: string[]
  published_at: string | null
  collected_at: string
  url: string | null
  analyzed: number
  latitude: number | null
  longitude: number | null
  magnitude: number | null
  severity: number | null
  tier: string | null
  is_noise: number | null
  gemini_rationale: string | null
}

export interface Report {
  report_id: string
  tier: string
  title: string
  situation: string
  impact: string
  action: string
  distro: string
  event_ids: string
  generated_at: string
  printed: number
}

export interface Stats {
  articles_today: number
  articles_total: number
  flash: number
  priority: number
  routine: number
  reports_today: number
  last_collected: string | null
}

export interface ChartPoint {
  hour: string
  count: number
}

export interface SourceHealth {
  status: "ok" | "fail" | "error" | "disabled"
  latency_ms: number | null
  error?: string
}

export interface PipelineStatus {
  collect: "idle" | "running"
  analyze: "idle" | "running"
  write: "idle" | "running"
}

export interface ChatReport {
  report_id: string
  title: string
  tier: string
  situation: string
  impact: string
  action: string
  distro: string
  generated_at: string
  sources: string[]
  query: string
  on_demand: boolean
}

export const api = {
  getArticles: (limit = 50, tier?: string) => {
    const params = new URLSearchParams({ limit: String(limit) })
    if (tier && tier !== "ALL") params.set("tier", tier)
    return fetchJSON<Article[]>(`/api/articles?${params}`)
  },

  getReports: (tier?: string, limit = 50) => {
    const params = new URLSearchParams({ limit: String(limit) })
    if (tier && tier !== "ALL") params.set("tier", tier)
    return fetchJSON<Report[]>(`/api/reports?${params}`)
  },

  getStats: () => fetchJSON<Stats>("/api/stats"),

  getChartEvents: () => fetchJSON<ChartPoint[]>("/api/chart/events"),

  getHealth: () => fetchJSON<Record<string, SourceHealth>>("/api/health"),

  getPipelineStatus: () => fetchJSON<PipelineStatus>("/api/pipeline/status"),

  triggerCollect: (source = "all") =>
    fetchJSON(`/api/pipeline/collect?source=${source}`, { method: "POST" }),

  triggerAnalyze: () =>
    fetchJSON("/api/pipeline/analyze", { method: "POST" }),

  triggerWrite: (tier = "all") =>
    fetchJSON(`/api/pipeline/write?tier=${tier}`, { method: "POST" }),

  chatIntel: (query: string) =>
    fetchJSON<ChatReport>("/api/chat", {
      method: "POST",
      body: JSON.stringify({ query }),
    }),
}

export function timeAgo(isoString: string | null): string {
  if (!isoString) return "—"
  const diff = Date.now() - new Date(isoString).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return "just now"
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  return `${Math.floor(hrs / 24)}d ago`
}
