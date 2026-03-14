"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { api } from "@/lib/api"
import type {
  Article,
  ChartPoint,
  PipelineStatus,
  Report,
  SourceHealth,
  Stats,
} from "@/lib/api"
import Sidebar from "@/components/Sidebar"
import FlashBanner from "@/components/FlashBanner"
import EventChart from "@/components/EventChart"
import LiveFeed from "@/components/LiveFeed"
import ReportWorkspace from "@/components/ReportWorkspace"

const REFRESH_INTERVAL_MS = 30_000
const POLL_INTERVAL_MS = 2_000

export default function DashboardPage() {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)

  const [stats, setStats] = useState<Stats | null>(null)
  const [health, setHealth] = useState<Record<string, SourceHealth> | null>(null)
  const [chartData, setChartData] = useState<ChartPoint[]>([])
  const [articles, setArticles] = useState<Article[]>([])
  const [reports, setReports] = useState<Report[]>([])
  const [pipelineStatus, setPipelineStatus] = useState<PipelineStatus | null>(null)

  const [articlesLoading, setArticlesLoading] = useState(true)
  const [reportsLoading, setReportsLoading] = useState(true)
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null)

  const refreshRef = useRef<ReturnType<typeof setInterval>>()
  const pollRef = useRef<ReturnType<typeof setInterval>>()

  const refresh = useCallback(async () => {
    try {
      const [a, r, s, c, h, ps] = await Promise.allSettled([
        api.getArticles(100),
        api.getReports("ALL", 100),
        api.getStats(),
        api.getChartEvents(),
        api.getHealth(),
        api.getPipelineStatus(),
      ])
      if (a.status === "fulfilled") setArticles(a.value)
      if (r.status === "fulfilled") setReports(r.value)
      if (s.status === "fulfilled") setStats(s.value)
      if (c.status === "fulfilled") setChartData(c.value)
      if (h.status === "fulfilled") setHealth(h.value)
      if (ps.status === "fulfilled") setPipelineStatus(ps.value)
      setLastRefresh(new Date())
    } catch (e) {
      console.error("Refresh error:", e)
    } finally {
      setArticlesLoading(false)
      setReportsLoading(false)
    }
  }, [])

  // Poll pipeline status every 2s while any stage is running, then refresh data when done
  const startPolling = useCallback((stage: string) => {
    if (pollRef.current) clearInterval(pollRef.current)
    pollRef.current = setInterval(async () => {
      try {
        const status = await api.getPipelineStatus()
        setPipelineStatus(status)
        const stageStatus = status[stage as keyof PipelineStatus]
        if (stageStatus === "idle") {
          clearInterval(pollRef.current)
          pollRef.current = undefined
          await refresh()
        }
      } catch (e) {
        console.error("Poll error:", e)
      }
    }, POLL_INTERVAL_MS)
  }, [refresh])

  useEffect(() => {
    refresh()
    refreshRef.current = setInterval(refresh, REFRESH_INTERVAL_MS)
    return () => {
      clearInterval(refreshRef.current)
      if (pollRef.current) clearInterval(pollRef.current)
    }
  }, [refresh])

  const flashReports = reports.filter((r) => r.tier === "FLASH")

  const handlePipelineAction = useCallback(
    async (stage: string, triggerFn: () => Promise<unknown>) => {
      try {
        await triggerFn()
        startPolling(stage)
      } catch (e) {
        console.error(`Pipeline ${stage} trigger failed:`, e)
      }
    },
    [startPolling]
  )

  return (
    <div className="flex h-screen overflow-hidden bg-bg-primary">
      <Sidebar
        stats={stats}
        health={health}
        collapsed={sidebarCollapsed}
        onToggle={() => setSidebarCollapsed((c) => !c)}
      />

      <div className="flex-1 flex flex-col overflow-hidden min-w-0">
        {/* Flash Banner */}
        <FlashBanner reports={flashReports} />

        {/* Chart */}
        <EventChart data={chartData} />

        {/* Main Content */}
        <div className="flex-1 flex overflow-hidden mt-3">
          <LiveFeed
            articles={articles}
            loading={articlesLoading}
            lastRefresh={lastRefresh}
            onRefresh={refresh}
          />

          <ReportWorkspace
            reports={reports}
            loading={reportsLoading}
            pipelineStatus={pipelineStatus}
            onCollect={(source) =>
              handlePipelineAction("collect", () => api.triggerCollect(source))
            }
            onAnalyze={() =>
              handlePipelineAction("analyze", () => api.triggerAnalyze())
            }
            onWrite={(tier) =>
              handlePipelineAction("write", () => api.triggerWrite(tier))
            }
          />
        </div>
      </div>
    </div>
  )
}
