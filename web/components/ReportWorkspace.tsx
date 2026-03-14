"use client"

import { useState, useRef } from "react"
import { Loader2, Play, Search, X, Sparkles } from "lucide-react"
import { clsx } from "clsx"
import type { Report, PipelineStatus, ChatReport } from "@/lib/api"
import { api, timeAgo } from "@/lib/api"
import ReportCard from "./ReportCard"

interface ReportWorkspaceProps {
  reports: Report[]
  loading: boolean
  pipelineStatus: PipelineStatus | null
  onCollect: (source: string) => Promise<void>
  onAnalyze: () => Promise<void>
  onWrite: (tier: string) => Promise<void>
}

const TIERS = ["ALL", "FLASH", "PRIORITY", "ROUTINE"] as const

export default function ReportWorkspace({
  reports,
  loading,
  pipelineStatus,
  onCollect,
  onAnalyze,
  onWrite,
}: ReportWorkspaceProps) {
  const [activeTier, setActiveTier] = useState<string>("ALL")
  const [chatQuery, setChatQuery] = useState("")
  const [chatLoading, setChatLoading] = useState(false)
  const [chatReports, setChatReports] = useState<ChatReport[]>([])
  const [chatError, setChatError] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const filtered =
    activeTier === "ALL"
      ? reports
      : reports.filter((r) => r.tier === activeTier)

  const flashCount = reports.filter((r) => r.tier === "FLASH").length

  const isRunning = (key: string) =>
    pipelineStatus?.[key as keyof PipelineStatus] === "running"

  async function handleChat(e: React.FormEvent) {
    e.preventDefault()
    const q = chatQuery.trim()
    if (!q || chatLoading) return

    setChatLoading(true)
    setChatError(null)
    try {
      const result = await api.chatIntel(q)
      setChatReports((prev) => [result, ...prev])
      setChatQuery("")
    } catch (err) {
      setChatError(err instanceof Error ? err.message : "Search failed")
    } finally {
      setChatLoading(false)
    }
  }

  function clearChat() {
    setChatReports([])
    setChatError(null)
  }

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      {/* Toolbar */}
      <div className="flex items-center gap-2 px-4 py-2.5 border-b border-bg-border shrink-0 flex-wrap">
        {/* Tier tabs */}
        <div className="flex gap-1 mr-2">
          {TIERS.map((t) => (
            <button
              key={t}
              onClick={() => setActiveTier(t)}
              className={clsx(
                "text-xs font-mono px-2.5 py-1 rounded transition-colors",
                activeTier === t
                  ? t === "ALL"
                    ? "bg-accent-blue text-white"
                    : t === "FLASH"
                    ? "bg-tier-flash-dim text-tier-flash border border-tier-flash-border"
                    : t === "PRIORITY"
                    ? "bg-tier-priority-dim text-tier-priority border border-tier-priority-border"
                    : "bg-tier-routine-dim text-tier-routine border border-tier-routine-border"
                  : "text-text-muted hover:text-text-primary hover:bg-bg-hover"
              )}
            >
              {t}
              {t === "FLASH" && flashCount > 0 && (
                <span className="ml-1 bg-tier-flash text-white text-xs rounded-full px-1">
                  {flashCount}
                </span>
              )}
            </button>
          ))}
        </div>

        {/* Pipeline actions */}
        <div className="flex gap-1.5 ml-auto">
          <PipelineButton
            label="Collect"
            loading={isRunning("collect")}
            onClick={() => onCollect("all")}
          />
          <PipelineButton
            label="Analyze"
            loading={isRunning("analyze")}
            onClick={() => onAnalyze()}
          />
          <PipelineButton
            label="Write"
            loading={isRunning("write")}
            onClick={() => onWrite("all")}
          />
        </div>
      </div>

      {/* Chat search bar */}
      <form
        onSubmit={handleChat}
        className="flex items-center gap-2 px-4 py-2 border-b border-bg-border shrink-0"
      >
        <Search className="w-3.5 h-3.5 text-text-dim shrink-0" />
        <input
          ref={inputRef}
          type="text"
          value={chatQuery}
          onChange={(e) => setChatQuery(e.target.value)}
          placeholder='Ask for intel... e.g. "Updates on Iran conflict"'
          disabled={chatLoading}
          className="flex-1 bg-transparent text-sm text-text-primary placeholder:text-text-dim outline-none font-mono"
        />
        {chatLoading && <Loader2 className="w-3.5 h-3.5 text-accent-blue animate-spin shrink-0" />}
        {chatReports.length > 0 && !chatLoading && (
          <button
            type="button"
            onClick={clearChat}
            className="text-text-dim hover:text-text-muted text-xs font-mono flex items-center gap-1"
            title="Clear on-demand reports"
          >
            <X className="w-3 h-3" />
            Clear
          </button>
        )}
        <button
          type="submit"
          disabled={chatLoading || !chatQuery.trim()}
          className={clsx(
            "text-xs font-mono px-2.5 py-1 rounded border transition-colors flex items-center gap-1",
            chatLoading || !chatQuery.trim()
              ? "border-bg-border text-text-dim cursor-not-allowed"
              : "border-accent-blue/40 text-accent-blue hover:bg-accent-blue-glow"
          )}
        >
          <Sparkles className="w-3 h-3" />
          Intel
        </button>
      </form>

      {/* Error */}
      {chatError && (
        <div className="px-4 py-2 text-xs text-tier-flash font-mono border-b border-bg-border">
          {chatError}
        </div>
      )}

      {/* Report list */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {/* On-demand chat reports */}
        {chatReports.map((cr) => (
          <OnDemandReportCard key={cr.report_id} report={cr} />
        ))}

        {/* Pipeline reports */}
        {loading && filtered.length === 0 && chatReports.length === 0 ? (
          <div className="flex items-center justify-center h-32 text-text-dim text-xs font-mono">
            Loading reports...
          </div>
        ) : filtered.length === 0 && chatReports.length === 0 ? (
          <EmptyState tier={activeTier} />
        ) : (
          filtered.map((r) => <ReportCard key={r.report_id} report={r} />)
        )}
      </div>
    </div>
  )
}

function OnDemandReportCard({ report }: { report: ChatReport }) {
  const TIER_STYLES: Record<string, { badge: string; border: string; header: string }> = {
    FLASH: {
      badge: "tier-badge-flash",
      border: "border-tier-flash-border",
      header: "text-tier-flash",
    },
    PRIORITY: {
      badge: "tier-badge-priority",
      border: "border-tier-priority-border",
      header: "text-tier-priority",
    },
    ROUTINE: {
      badge: "tier-badge-routine",
      border: "border-tier-routine-border",
      header: "text-tier-routine",
    },
  }
  const styles = TIER_STYLES[report.tier] ?? TIER_STYLES.ROUTINE

  return (
    <article
      className={clsx(
        "glass-card border p-4 animate-fade-in relative",
        styles.border
      )}
    >
      {/* On-demand badge */}
      <div className="absolute top-2 right-2">
        <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-accent-blue/20 text-accent-blue border border-accent-blue/30 flex items-center gap-1">
          <Sparkles className="w-2.5 h-2.5" />
          ON-DEMAND
        </span>
      </div>

      {/* Query context */}
      <div className="text-[11px] font-mono text-text-dim mb-2">
        <Search className="w-3 h-3 inline mr-1" />
        &quot;{report.query}&quot;
      </div>

      {/* Header */}
      <div className="flex items-start gap-2 mb-3">
        <span className={styles.badge}>{report.tier}</span>
        <h3 className={clsx("text-sm font-semibold leading-snug", styles.header)}>
          {report.title}
        </h3>
      </div>

      {/* Sections */}
      <div className="space-y-2.5 text-sm">
        <Section label="SITUATION" text={report.situation} />
        <Section label="IMPACT" text={report.impact} />
        <Section label="ACTION" text={report.action} />
        {report.distro && (
          <div className="mt-1 px-2 py-1 rounded border border-bg-border bg-bg-secondary/40 text-xs font-mono text-text-dim">
            DISTRO: <span className="text-text-secondary italic">{report.distro}</span>
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="flex items-center gap-3 mt-3 pt-3 border-t border-bg-border">
        <span className="text-text-dim text-xs font-mono">
          {timeAgo(report.generated_at)}
        </span>
        {report.sources.length > 0 && (
          <span className="text-text-dim text-xs font-mono">
            {report.sources.length} web source{report.sources.length !== 1 ? "s" : ""}
          </span>
        )}
      </div>
    </article>
  )
}

function PipelineButton({
  label,
  loading,
  onClick,
}: {
  label: string
  loading: boolean
  onClick: () => void
}) {
  return (
    <button
      onClick={onClick}
      disabled={loading}
      className={clsx(
        "flex items-center gap-1.5 text-xs font-mono px-2.5 py-1.5 rounded border transition-colors",
        loading
          ? "border-accent-blue/40 text-accent-blue bg-accent-blue-glow cursor-not-allowed"
          : "border-bg-border text-text-muted hover:border-accent-blue hover:text-accent-blue hover:bg-accent-blue-glow"
      )}
    >
      {loading ? (
        <Loader2 className="w-3 h-3 animate-spin" />
      ) : (
        <Play className="w-3 h-3" />
      )}
      {label}
    </button>
  )
}

function Section({ label, text }: { label: string; text: string }) {
  if (!text) return null
  return (
    <div>
      <span className="text-text-dim text-xs font-mono font-bold uppercase tracking-wider">
        {label}:{" "}
      </span>
      <span className="text-text-primary">{text}</span>
    </div>
  )
}

function EmptyState({ tier }: { tier: string }) {
  const msg =
    tier === "ALL"
      ? "No reports yet. Run the pipeline or search for intel above."
      : `No ${tier} reports found.`
  return (
    <div className="flex flex-col items-center justify-center h-48 gap-2 text-center">
      <p className="text-text-muted text-sm">{msg}</p>
      <p className="text-text-dim text-xs font-mono">
        Collect → Analyze → Write | or search for on-demand intel
      </p>
    </div>
  )
}
