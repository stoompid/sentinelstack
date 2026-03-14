"use client"

import { clsx } from "clsx"
import { ExternalLink, RefreshCw } from "lucide-react"
import type { Article } from "@/lib/api"
import { timeAgo } from "@/lib/api"

interface LiveFeedProps {
  articles: Article[]
  loading: boolean
  lastRefresh: Date | null
  onRefresh: () => void
}

const SOURCE_COLORS: Record<string, string> = {
  osac: "text-blue-400",
  reliefweb: "text-purple-400",
  usgs: "text-orange-400",
  gdacs: "text-yellow-400",
}

const TIER_DOT: Record<string, string> = {
  FLASH: "bg-tier-flash",
  PRIORITY: "bg-tier-priority",
  ROUTINE: "bg-tier-routine",
}

export default function LiveFeed({
  articles,
  loading,
  lastRefresh,
  onRefresh,
}: LiveFeedProps) {
  return (
    <div className="flex flex-col w-80 shrink-0 border-r border-bg-border overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2.5 border-b border-bg-border shrink-0">
        <div>
          <span className="text-text-primary text-sm font-semibold">Live Feed</span>
          {lastRefresh && (
            <span className="text-text-dim text-xs font-mono ml-2">
              {timeAgo(lastRefresh.toISOString())}
            </span>
          )}
        </div>
        <button
          onClick={onRefresh}
          disabled={loading}
          className="text-text-muted hover:text-accent-blue transition-colors disabled:opacity-40"
          title="Refresh feed"
        >
          <RefreshCw className={clsx("w-3.5 h-3.5", loading && "animate-spin")} />
        </button>
      </div>

      {/* Feed */}
      <div className="flex-1 overflow-y-auto">
        {loading && articles.length === 0 ? (
          <div className="flex items-center justify-center h-32 text-text-dim text-xs font-mono">
            Loading...
          </div>
        ) : articles.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-32 gap-1 text-text-dim text-xs font-mono">
            <span>No articles yet</span>
            <span>Run a collection to populate</span>
          </div>
        ) : (
          <div className="divide-y divide-bg-border">
            {articles.map((a) => (
              <FeedItem key={a.article_id} article={a} />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function FeedItem({ article }: { article: Article }) {
  const tierDot = article.tier ? TIER_DOT[article.tier] : null
  const sourceColor = SOURCE_COLORS[article.source] ?? "text-text-muted"

  return (
    <div className="px-3 py-2.5 hover:bg-bg-hover transition-colors group animate-slide-in">
      <div className="flex items-start gap-2">
        {/* Tier indicator */}
        <div className="mt-1.5 shrink-0">
          {tierDot ? (
            <div className={clsx("w-1.5 h-1.5 rounded-full", tierDot)} />
          ) : (
            <div className="w-1.5 h-1.5 rounded-full bg-text-dim" />
          )}
        </div>

        <div className="flex-1 min-w-0">
          {/* Title */}
          <div className="flex items-start gap-1">
            <p className="text-text-primary text-xs leading-snug line-clamp-2 flex-1">
              {article.title}
            </p>
            {article.url && (
              <a
                href={article.url}
                target="_blank"
                rel="noopener noreferrer"
                className="shrink-0 text-text-dim hover:text-accent-blue opacity-0 group-hover:opacity-100 transition-opacity mt-0.5"
              >
                <ExternalLink className="w-2.5 h-2.5" />
              </a>
            )}
          </div>

          {/* Meta */}
          <div className="flex items-center gap-1.5 mt-1 flex-wrap">
            <span className={clsx("text-xs font-mono uppercase", sourceColor)}>
              {article.source}
            </span>
            {article.country && (
              <>
                <span className="text-text-dim text-xs">·</span>
                <span className="text-text-muted text-xs">{article.country}</span>
              </>
            )}
            {article.magnitude != null && (
              <>
                <span className="text-text-dim text-xs">·</span>
                <span className="text-orange-400 text-xs font-mono">
                  M{article.magnitude.toFixed(1)}
                </span>
              </>
            )}
            <span className="text-text-dim text-xs ml-auto">
              {timeAgo(article.collected_at)}
            </span>
          </div>

          {/* Severity */}
          {article.severity != null && (
            <div className="flex items-center gap-1 mt-1">
              <SeverityBar severity={article.severity} />
              <span className="text-text-dim text-xs font-mono">
                {article.severity}/10
              </span>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function SeverityBar({ severity }: { severity: number }) {
  const color =
    severity >= 8
      ? "bg-tier-flash"
      : severity >= 5
      ? "bg-tier-priority"
      : "bg-tier-routine"
  const width = `${(severity / 10) * 100}%`

  return (
    <div className="flex-1 h-0.5 bg-bg-border rounded-full overflow-hidden">
      <div
        className={clsx("h-full rounded-full", color)}
        style={{ width }}
      />
    </div>
  )
}
