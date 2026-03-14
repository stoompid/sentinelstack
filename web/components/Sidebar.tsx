"use client"

import { useState } from "react"
import Link from "next/link"
import { usePathname } from "next/navigation"
import {
  LayoutDashboard,
  Settings,
  Shield,
  ChevronLeft,
  ChevronRight,
  Radio,
} from "lucide-react"
import type { Stats, SourceHealth } from "@/lib/api"
import { clsx } from "clsx"

interface SidebarProps {
  stats: Stats | null
  health: Record<string, SourceHealth> | null
  collapsed: boolean
  onToggle: () => void
}

const SOURCE_LABELS: Record<string, string> = {
  un_news: "UN News",
  bbc: "BBC World",
  usgs: "USGS",
  gdacs: "GDACS",
  nws: "NWS",
}

const NAV_LINKS = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/settings", label: "Settings", icon: Settings },
]

export default function Sidebar({
  stats,
  health,
  collapsed,
  onToggle,
}: SidebarProps) {
  const pathname = usePathname()

  return (
    <aside
      className={clsx(
        "flex flex-col h-full bg-bg-surface border-r border-bg-border transition-all duration-200 shrink-0",
        collapsed ? "w-14" : "w-56"
      )}
    >
      {/* Logo */}
      <div className="flex items-center gap-2.5 px-3 py-4 border-b border-bg-border">
        <div className="shrink-0 w-7 h-7 rounded bg-accent-blue flex items-center justify-center">
          <Shield className="w-4 h-4 text-white" />
        </div>
        {!collapsed && (
          <div>
            <div className="text-text-primary font-semibold text-sm leading-none">
              SentinelTower
            </div>
            <div className="text-text-muted text-xs mt-0.5 font-mono">GSOC</div>
          </div>
        )}
      </div>

      {/* Nav */}
      <nav className="flex-1 py-3 space-y-0.5 px-2">
        {NAV_LINKS.map(({ href, label, icon: Icon }) => {
          const active = pathname === href
          return (
            <Link
              key={href}
              href={href}
              className={clsx(
                "flex items-center gap-2.5 px-2 py-2 rounded text-sm transition-colors duration-100",
                active
                  ? "bg-accent-blue-glow text-accent-blue"
                  : "text-text-muted hover:text-text-primary hover:bg-bg-hover"
              )}
              title={collapsed ? label : undefined}
            >
              <Icon className="w-4 h-4 shrink-0" />
              {!collapsed && <span>{label}</span>}
            </Link>
          )
        })}
      </nav>

      {/* Source Health */}
      {!collapsed && (
        <div className="px-3 pb-3">
          <div className="section-label">Sources</div>
          <div className="space-y-1.5">
            {Object.entries(SOURCE_LABELS).map(([key, label]) => {
              const h = health?.[key]
              const status = h?.status ?? "unknown"
              return (
                <div key={key} className="flex items-center gap-2">
                  <div
                    className={clsx(
                      "w-1.5 h-1.5 rounded-full shrink-0",
                      status === "ok"
                        ? "bg-green-400"
                        : status === "disabled"
                        ? "bg-text-dim"
                        : "bg-tier-flash"
                    )}
                  />
                  <span className="text-text-muted text-xs font-mono">
                    {label}
                  </span>
                  {h?.latency_ms != null && (
                    <span className="text-text-dim text-xs font-mono ml-auto">
                      {h.latency_ms}ms
                    </span>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Stats */}
      {!collapsed && stats && (
        <div className="px-3 pb-3 border-t border-bg-border pt-3">
          <div className="section-label">Today</div>
          <div className="grid grid-cols-2 gap-1.5">
            <StatPill label="Events" value={stats.articles_today} />
            <StatPill label="Reports" value={stats.reports_today} />
            <StatPill
              label="FLASH"
              value={stats.flash}
              color="text-tier-flash"
            />
            <StatPill
              label="PRIOR"
              value={stats.priority}
              color="text-tier-priority"
            />
          </div>
        </div>
      )}

      {/* Collapse toggle */}
      <button
        onClick={onToggle}
        className="flex items-center justify-center py-3 border-t border-bg-border text-text-dim hover:text-text-muted transition-colors"
        title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
      >
        {collapsed ? (
          <ChevronRight className="w-3.5 h-3.5" />
        ) : (
          <ChevronLeft className="w-3.5 h-3.5" />
        )}
      </button>
    </aside>
  )
}

function StatPill({
  label,
  value,
  color = "text-text-primary",
}: {
  label: string
  value: number
  color?: string
}) {
  return (
    <div className="bg-bg-primary rounded px-2 py-1.5">
      <div className={clsx("text-sm font-mono font-bold", color)}>{value}</div>
      <div className="text-text-dim text-xs">{label}</div>
    </div>
  )
}
