import { useState, useEffect, useRef, useCallback } from 'react'
import { Globe, RefreshCw, Maximize2, Minimize2, X, ExternalLink } from 'lucide-react'
import { agentApi } from '../api/client'
import { invoke } from '@tauri-apps/api/core'

interface BrowserEvent {
  name: string
  args: Record<string, string>
}

interface Props {
  agentId: number
  browserEvents: BrowserEvent[]
  onClose?: () => void
}

export default function BrowserPanel({ agentId, browserEvents, onClose }: Props) {
  const [screenshotUrl, setScreenshotUrl] = useState<string | null>(null)
  const [currentUrl, setCurrentUrl] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [expanded, setExpanded] = useState(false)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const lastEventCount = useRef(0)

  const fetchState = useCallback(async () => {
    try {
      const state = await agentApi.browserState(agentId)
      if (state.url) {
        setCurrentUrl(state.url)
      }
      if (state.has_screenshot) {
        // Add timestamp to bust cache
        setScreenshotUrl(`/api/agents/${agentId}/browser/screenshot?t=${Date.now()}`)
      }
    } catch {
      // Ignore errors — screenshot may not exist yet
    }
  }, [agentId])

  // Poll for screenshot updates when there are browser events
  useEffect(() => {
    if (browserEvents.length > lastEventCount.current) {
      lastEventCount.current = browserEvents.length
      setLoading(true)
      // Small delay to let screenshot save on backend
      const timeout = setTimeout(() => {
        fetchState().finally(() => setLoading(false))
      }, 800)
      return () => clearTimeout(timeout)
    }
  }, [browserEvents, fetchState])

  // Periodic polling fallback — only when there are active browser events
  useEffect(() => {
    if (browserEvents.length === 0) {
      if (pollRef.current) {
        clearInterval(pollRef.current)
        pollRef.current = null
      }
      return
    }
    if (!pollRef.current) {
      pollRef.current = setInterval(() => {
        fetchState()
      }, 3000)
    }
    return () => {
      if (pollRef.current) {
        clearInterval(pollRef.current)
        pollRef.current = null
      }
    }
  }, [browserEvents.length, fetchState])

  // Initial fetch
  useEffect(() => {
    fetchState()
  }, [fetchState])

  const containerClass = expanded
    ? 'fixed inset-4 z-[60] bg-white rounded-xl shadow-2xl flex flex-col overflow-hidden border border-gray-200'
    : 'w-full h-full flex flex-col bg-white border-l border-gray-200'

  return (
    <div className={containerClass}>
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-gray-200 bg-gray-50">
        <div className="flex items-center gap-2 min-w-0">
          <Globe size={14} className="text-blue-600 flex-shrink-0" />
          <span className="text-xs font-medium text-gray-700 truncate">
            {currentUrl || 'Browser idle'}
          </span>
        </div>
        <div className="flex items-center gap-1 flex-shrink-0">
          <button
            onClick={() => {
              setLoading(true)
              fetchState().finally(() => setLoading(false))
            }}
            className="p-1 hover:bg-gray-200 rounded text-gray-500"
            title="刷新截图"
          >
            <RefreshCw size={12} className={loading ? 'animate-spin' : ''} />
          </button>
          <button
            onClick={() => setExpanded(v => !v)}
            className="p-1 hover:bg-gray-200 rounded text-gray-500"
            title={expanded ? '缩小' : '放大'}
          >
            {expanded ? <Minimize2 size={12} /> : <Maximize2 size={12} />}
          </button>
          {currentUrl && (
            <button
              onClick={async () => {
                try {
                  await invoke('open_browser_window', { url: currentUrl })
                } catch {
                  window.open(currentUrl, '_blank')
                }
              }}
              className="p-1 hover:bg-gray-200 rounded text-gray-500"
              title="在新窗口打开"
            >
              <ExternalLink size={12} />
            </button>
          )}
          {onClose && !expanded && (
            <button onClick={onClose} className="p-1 hover:bg-gray-200 rounded text-gray-500">
              <X size={12} />
            </button>
          )}
          {expanded && (
            <button onClick={() => setExpanded(false)} className="p-1 hover:bg-gray-200 rounded text-gray-500">
              <X size={12} />
            </button>
          )}
        </div>
      </div>

      {/* URL bar */}
      {currentUrl && (
        <div className="px-3 py-1.5 bg-white border-b border-gray-100">
          <div className="text-[10px] text-gray-500 truncate font-mono bg-gray-50 px-2 py-1 rounded">
            {currentUrl}
          </div>
        </div>
      )}

      {/* Screenshot */}
      <div className="flex-1 overflow-auto bg-gray-100 flex items-center justify-center relative">
        {screenshotUrl ? (
          <img
            src={screenshotUrl}
            alt="Browser screenshot"
            className="max-w-full max-h-full object-contain shadow-sm"
            onLoad={() => setLoading(false)}
          />
        ) : (
          <div className="text-center text-gray-400 text-xs px-4">
            {browserEvents.length > 0 ? (
              <>
                <div className="mb-2">🌐 浏览器正在运行</div>
                <div>等待截图生成...</div>
              </>
            ) : (
              <>
                <div className="mb-2">🌐 Browser Panel</div>
                <div>当 Agent 使用浏览器工具时，<br />截图将显示在这里</div>
              </>
            )}
          </div>
        )}
        {loading && (
          <div className="absolute inset-0 bg-white/50 flex items-center justify-center">
            <span className="inline-block w-5 h-5 border-2 border-gray-300 border-t-gray-600 rounded-full animate-spin" />
          </div>
        )}
      </div>

      {/* Event log */}
      {browserEvents.length > 0 && (
        <div className="px-3 py-2 border-t border-gray-200 bg-gray-50 max-h-24 overflow-y-auto">
          <div className="text-[10px] text-gray-400 mb-1">操作记录</div>
          <div className="space-y-1">
            {browserEvents.slice(-5).map((ev, i) => (
              <div key={i} className="text-[10px] text-gray-600 flex items-center gap-1">
                <span className="bg-blue-100 text-blue-700 px-1 rounded">{ev.name.replace('browser_', '')}</span>
                {Object.entries(ev.args).map(([k, v]) => (
                  <span key={k} className="truncate max-w-[120px]">{k}={String(v).slice(0, 30)}</span>
                ))}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
