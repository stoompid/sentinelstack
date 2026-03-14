"use client"

import { useState } from "react"
import { AlertTriangle, X } from "lucide-react"
import type { Report } from "@/lib/api"

interface FlashBannerProps {
  reports: Report[]
}

export default function FlashBanner({ reports }: FlashBannerProps) {
  const [dismissed, setDismissed] = useState(false)

  if (dismissed || reports.length === 0) return null

  const latest = reports[0]

  return (
    <div className="relative flex items-center gap-3 px-4 py-2.5 bg-red-950/60 border-b border-tier-flash-border animate-flash-pulse">
      <AlertTriangle className="w-4 h-4 text-tier-flash shrink-0" />
      <div className="flex-1 min-w-0">
        <span className="text-tier-flash font-mono font-bold text-xs uppercase tracking-wider mr-2">
          FLASH
        </span>
        <span className="text-red-200 text-sm truncate">{latest.title}</span>
        {reports.length > 1 && (
          <span className="text-red-400 text-xs ml-2">
            +{reports.length - 1} more
          </span>
        )}
      </div>
      <button
        onClick={() => setDismissed(true)}
        className="text-red-400 hover:text-red-200 transition-colors shrink-0"
        aria-label="Dismiss alert"
      >
        <X className="w-4 h-4" />
      </button>
    </div>
  )
}
