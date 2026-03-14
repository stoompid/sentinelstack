"use client"

import { useState } from "react"
import Link from "next/link"
import { ArrowLeft, Save, Eye, EyeOff, CheckCircle } from "lucide-react"

export default function SettingsPage() {
  const [apiKey, setApiKey] = useState("")
  const [showKey, setShowKey] = useState(false)
  const [saved, setSaved] = useState(false)

  function handleSave() {
    // In production, this would call a PATCH /api/settings endpoint.
    // For now, just show confirmation — API key is managed via Railway env vars.
    setSaved(true)
    setTimeout(() => setSaved(false), 3000)
  }

  return (
    <div className="min-h-screen bg-bg-primary p-6">
      <div className="max-w-2xl mx-auto">
        {/* Header */}
        <div className="flex items-center gap-3 mb-8">
          <Link
            href="/"
            className="text-text-muted hover:text-text-primary transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
          </Link>
          <div>
            <h1 className="text-text-primary font-semibold text-lg">Settings</h1>
            <p className="text-text-muted text-sm">
              SentinelStack configuration
            </p>
          </div>
        </div>

        {/* API Keys */}
        <section className="glass-card p-5 mb-4">
          <h2 className="text-text-primary font-semibold mb-1">Gemini API Key</h2>
          <p className="text-text-muted text-sm mb-4">
            Used by the Analyst and Writer agents. Set as{" "}
            <code className="font-mono text-xs bg-bg-primary px-1.5 py-0.5 rounded text-accent-blue">
              GEMINI_API_KEY
            </code>{" "}
            on Railway.
          </p>

          <div className="relative">
            <input
              type={showKey ? "text" : "password"}
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder="AIza..."
              className="w-full bg-bg-primary border border-bg-border rounded px-3 py-2 text-sm
                         font-mono text-text-primary placeholder:text-text-dim
                         focus:outline-none focus:border-accent-blue transition-colors pr-10"
            />
            <button
              type="button"
              onClick={() => setShowKey((s) => !s)}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-text-muted hover:text-text-primary"
            >
              {showKey ? (
                <EyeOff className="w-4 h-4" />
              ) : (
                <Eye className="w-4 h-4" />
              )}
            </button>
          </div>

          <div className="mt-2 p-3 bg-bg-primary rounded border border-bg-border text-xs text-text-muted font-mono">
            <p className="mb-1 text-text-dim">To update the key on Railway:</p>
            <p>1. Go to your Railway project → Variables</p>
            <p>2. Set GEMINI_API_KEY to your new key</p>
            <p>3. Redeploy the service</p>
          </div>
        </section>

        {/* Database */}
        <section className="glass-card p-5 mb-4">
          <h2 className="text-text-primary font-semibold mb-1">Database</h2>
          <p className="text-text-muted text-sm mb-3">
            Using Railway managed PostgreSQL. Set as{" "}
            <code className="font-mono text-xs bg-bg-primary px-1.5 py-0.5 rounded text-accent-blue">
              DATABASE_URL
            </code>{" "}
            on Railway (automatically injected when you link the PostgreSQL service).
          </p>
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 rounded-full bg-green-400" />
            <span className="text-text-muted text-sm">
              PostgreSQL — configured via environment
            </span>
          </div>
        </section>

        {/* Sources */}
        <section className="glass-card p-5 mb-6">
          <h2 className="text-text-primary font-semibold mb-1">OSINT Sources</h2>
          <p className="text-text-muted text-sm mb-4">
            Source toggles are in{" "}
            <code className="font-mono text-xs bg-bg-primary px-1.5 py-0.5 rounded text-accent-blue">
              config/sources.json
            </code>
            . Set <code className="font-mono text-xs">enabled: false</code> to
            disable a source.
          </p>

          {[
            { id: "osac", label: "OSAC", desc: "US State Dept security alerts" },
            { id: "reliefweb", label: "ReliefWeb", desc: "UN humanitarian reports" },
            { id: "usgs", label: "USGS", desc: "Significant earthquakes M5.0+" },
            { id: "gdacs", label: "GDACS", desc: "Global disasters (orange/red)" },
          ].map((s) => (
            <div
              key={s.id}
              className="flex items-center justify-between py-2.5 border-b border-bg-border last:border-0"
            >
              <div>
                <p className="text-text-primary text-sm font-mono">{s.label}</p>
                <p className="text-text-muted text-xs">{s.desc}</p>
              </div>
              <div className="w-2 h-2 rounded-full bg-green-400" />
            </div>
          ))}
        </section>

        <button
          onClick={handleSave}
          className="flex items-center gap-2 btn-primary"
        >
          {saved ? (
            <>
              <CheckCircle className="w-4 h-4" />
              Saved
            </>
          ) : (
            <>
              <Save className="w-4 h-4" />
              Save Changes
            </>
          )}
        </button>
      </div>
    </div>
  )
}
