"use client"

import { clsx } from "clsx"
import { Clock } from "lucide-react"
import type { Report } from "@/lib/api"
import { timeAgo } from "@/lib/api"

interface ReportCardProps {
  report: Report
}

const TIER_STYLES = {
  FLASH: {
    badge: "tier-badge-flash",
    border: "border-tier-flash-border",
    glow: "flash-glow",
    header: "text-tier-flash",
  },
  PRIORITY: {
    badge: "tier-badge-priority",
    border: "border-tier-priority-border",
    glow: "",
    header: "text-tier-priority",
  },
  ROUTINE: {
    badge: "tier-badge-routine",
    border: "border-tier-routine-border",
    glow: "",
    header: "text-tier-routine",
  },
}

export default function ReportCard({ report }: ReportCardProps) {
  const styles = TIER_STYLES[report.tier as keyof typeof TIER_STYLES] ?? TIER_STYLES.ROUTINE
  const sourceCount = report.event_ids ? report.event_ids.split(",").length : 0

  return (
    <article
      className={clsx(
        "glass-card border p-4 animate-fade-in",
        styles.border,
        styles.glow
      )}
    >
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
        {/* distro removed from display */}
      </div>

      {/* Footer */}
      <div className="flex items-center gap-3 mt-3 pt-3 border-t border-bg-border">
        <div className="flex items-center gap-1 text-text-dim text-xs font-mono">
          <Clock className="w-3 h-3" />
          <span>{timeAgo(report.generated_at)}</span>
        </div>
        {sourceCount > 0 && (
          <span className="text-text-dim text-xs font-mono">
            {sourceCount} event{sourceCount !== 1 ? "s" : ""}
          </span>
        )}
      </div>
    </article>
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
