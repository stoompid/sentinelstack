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

const REFRESH_IDLE_MS = 15_000
const REFRESH_ACTIVE_MS = 3_000

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

  const refreshRef = useRef<ReturnType<typeof setTimeout>>()
  const pipelineStatusRef = useRef<PipelineStatus | null>(null)

  const scheduleNext = useCallback((status: PipelineStatus | null) => {
    clearTimeout(refreshRef.current)
    const isRunning = status
      ? Object.values(status).some(Boolean)
      : false
    const delay = isRunning ? REFRESH_ACTIVE_MS : REFRESH_IDLE_MS
    refreshRef.current = setTimeout(doRefresh, delay)
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const doRefresh = useCallback(async () => {
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
      const latestStatus = ps.status === "fulfilled" ? ps.value : null
      if (ps.status === "fulfilled") {
        setPipelineStatus(latestStatus)
        pipelineStatusRef.current = latestStatus
      }
      setLastRefresh(new Date())
      scheduleNext(latestStatus ?? pipelineStatusRef.current)
    } catch (e) {
      console.error("Refresh error:", e)
      scheduleNext(pipelineStatusRef.current)
    } finally {
      setArticlesLoading(false)
      setReportsLoading(false)
    }
  }, [scheduleNext])

  const refresh = useCallback(() => {
    clearTimeout(refreshRef.current)
    doRefresh()
  }, [doRefresh])

  useEffect(() => {
    doRefresh()
    return () => clearTimeout(refreshRef.current)
  }, [doRefresh])

  const flashReports = reports.filter((r) => r.tier === "FLASH")

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
          />
        </div>
      </div>
    </div>
  )
}
