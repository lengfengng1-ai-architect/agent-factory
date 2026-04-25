import { useState, useRef, useEffect, useCallback } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Bot, User, Send, X, FileText, BookOpen, MessageCircle, Copy, Check, Globe } from 'lucide-react'
import type { Agent, ChatFile, Source } from '../types'
import { chatApi, fileApi, summaryApi, feishuApi } from '../api/client'
import ChatFileBar, { type FileMode } from './ChatFileBar'
import BrowserPanel from './BrowserPanel'

interface Message {
  role: 'user' | 'assistant'
  content: string
  fileIds?: string[]
  reasoning?: string
  toolCalls?: string[]
  sources?: Source[]
  attachments?: { type: string; file_id: string; name: string }[]
}

interface BrowserEvent {
  name: string
  args: Record<string, string>
}

interface BrowserStatus {
  state: 'navigating' | 'reading' | 'idle'
  url?: string
}

interface Props {
  agent: Agent
  onClose: () => void
}

const STORAGE_KEY = (agentId: number) => `chat_file_mode_agent_${agentId}`

export default function ChatModal({ agent, onClose }: Props) {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [files, setFiles] = useState<ChatFile[]>([])
  const [uploading, setUploading] = useState(false)
  const [fileMode, setFileMode] = useState<FileMode>(() => {
    const saved = localStorage.getItem(STORAGE_KEY(agent.id))
    return (saved as FileMode) || 'auto'
  })
  const bottomRef = useRef<HTMLDivElement>(null)
  const [showSummaryPanel, setShowSummaryPanel] = useState(false)
  const [selectedSummaries, setSelectedSummaries] = useState<number[]>([])
  const [activeTab, setActiveTab] = useState<'chat' | 'feishu'>('chat')
  const [copiedIdx, setCopiedIdx] = useState<number | null>(null)
  const [showBrowser, setShowBrowser] = useState(false)
  const [browserEvents, setBrowserEvents] = useState<BrowserEvent[]>([])
  const [browserStatus, setBrowserStatus] = useState<BrowserStatus>({ state: 'idle' })

  // Use refs for streaming accumulation to avoid excessive re-renders
  const contentRef = useRef('')
  const reasoningRef = useRef('')
  const toolCallsRef = useRef<string[]>([])
  const browserEventsRef = useRef<BrowserEvent[]>([])
  const browserStatusRef = useRef<BrowserStatus>({ state: 'idle' })
  const rafPending = useRef(false)

  useEffect(() => {
    if (activeTab === 'feishu' && !agent.config?.feishu?.enabled) {
      setActiveTab('chat')
    }
  }, [activeTab, agent.config?.feishu?.enabled])

  const { data: historyData, isLoading: historyLoading } = useQuery({
    queryKey: ['chat_history', agent.id],
    queryFn: () => chatApi.history(agent.id),
    enabled: !!agent.id && activeTab === 'chat',
    refetchOnWindowFocus: false,
    staleTime: Infinity,
  })

  const { data: feishuHistoryData, isLoading: feishuHistoryLoading } = useQuery({
    queryKey: ['feishu_history', agent.id],
    queryFn: () => feishuApi.history(agent.id),
    enabled: !!agent.id && activeTab === 'feishu',
  })

  // Load existing files
  const { data: filesData } = useQuery({
    queryKey: ['chat_files', agent.id],
    queryFn: () => fileApi.listAgent(agent.id),
    enabled: !!agent.id,
  })

  const { data: summariesData } = useQuery({
    queryKey: ['summaries', agent.id],
    queryFn: () => summaryApi.list({ agent_id: agent.id, limit: 20 }),
    enabled: !!agent.id && showSummaryPanel,
  })

  useEffect(() => {
    if (filesData?.files) {
      setFiles(filesData.files)
    }
  }, [filesData])

  useEffect(() => {
    // Sync server history into local state only when history data actually changes
    // AND local messages are empty. This prevents:
    // 1. Race: historyData arrives during streaming → wipes accumulated content
    // 2. Double-sync: React Query cache hit on mount doesn't re-trigger effect
    if (historyData?.messages) {
      setMessages(prev => {
        if (prev.length > 0) return prev
        return historyData.messages.map(m => ({
          role: m.role as 'user' | 'assistant',
          content: m.content,
          sources: m.sources,
        }))
      })
    }
  }, [historyData])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleModeChange = useCallback((mode: FileMode) => {
    setFileMode(mode)
    localStorage.setItem(STORAGE_KEY(agent.id), mode)
  }, [agent.id])

  const handleUpload = useCallback(async (fileList: FileList) => {
    setUploading(true)
    try {
      const res = await fileApi.uploadAgent(agent.id, fileList)
      if (res.files) {
        setFiles(prev => [...prev, ...res.files])
      }
    } catch (err: any) {
      alert(`上传失败: ${err.message || 'Unknown error'}`)
    } finally {
      setUploading(false)
    }
  }, [agent.id])

  const handleRemoveFile = useCallback(async (fileId: string) => {
    try {
      await fileApi.deleteAgent(agent.id, fileId)
      setFiles(prev => prev.filter(f => f.id !== fileId))
    } catch (err: any) {
      alert(`删除失败: ${err.message || 'Unknown error'}`)
    }
  }, [agent.id])

  function getDomain(url: string): string {
    try {
      return new URL(url).hostname
    } catch {
      return url
    }
  }

  const handleCopy = async (text: string, idx: number) => {
    try {
      await navigator.clipboard.writeText(text)
      setCopiedIdx(idx)
      setTimeout(() => setCopiedIdx(null), 2000)
    } catch {
      // ignore
    }
  }

  const handleSend = async () => {
    const text = input.trim()
    if (!text || loading) return

    const activeFileIds = files.map(f => f.id)

    setInput('')
    setMessages(prev => [...prev, { role: 'user', content: text, fileIds: activeFileIds }])
    setLoading(true)

    // Add placeholder assistant message
    setMessages(prev => [...prev, { role: 'assistant', content: '', reasoning: '', toolCalls: [] }])

    contentRef.current = ''
    reasoningRef.current = ''
    toolCallsRef.current = []
    browserEventsRef.current = []

    const flushToState = () => {
      rafPending.current = false
      setMessages(prev => {
        const next = [...prev]
        const last = next[next.length - 1]
        if (last && last.role === 'assistant') {
          next[next.length - 1] = {
            ...last,
            content: contentRef.current,
            reasoning: reasoningRef.current || undefined,
            toolCalls: toolCallsRef.current.length > 0 ? [...toolCallsRef.current] : undefined,
          }
        }
        return next
      })
    }

    const scheduleFlush = () => {
      if (!rafPending.current) {
        rafPending.current = true
        requestAnimationFrame(flushToState)
      }
    }

    try {
      const res = await fetch(`/api/agents/${agent.id}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: text,
          files: activeFileIds,
          file_mode: fileMode,
        }),
      })

      if (!res.ok || !res.body) {
        setMessages(prev => {
          const next = [...prev]
          next[next.length - 1] = { role: 'assistant', content: `Error: ${res.statusText || 'Failed to connect'}` }
          return next
        })
        setLoading(false)
        return
      }

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const parts = buffer.split('\n\n')
        buffer = parts.pop() || ''

        for (const part of parts) {
          const trimmed = part.trim()
          if (!trimmed.startsWith('data: ')) continue
          const data = trimmed.slice(6)
          if (data === '[DONE]') continue

          try {
            const parsed = JSON.parse(data) as {
              content?: string
              reasoning?: string
              tool_calls?: string[]
              error?: string
              browser_event?: BrowserEvent
              browser_status?: BrowserStatus
              sources?: Source[]
            }
            if (parsed.error) {
              setMessages(prev => {
                const last = prev[prev.length - 1]
                if (last && last.role === 'assistant') {
                  return [...prev.slice(0, -1), { ...last, content: last.content + `\n[Error: ${parsed.error}]` }]
                }
                return prev
              })
              continue
            }
            if (parsed.reasoning) {
              reasoningRef.current += parsed.reasoning
              scheduleFlush()
            }
            if (parsed.content) {
              contentRef.current += parsed.content
              scheduleFlush()
            }
            if (parsed.tool_calls && parsed.tool_calls.length > 0) {
              for (const tc of parsed.tool_calls) {
                if (!toolCallsRef.current.includes(tc)) {
                  toolCallsRef.current.push(tc)
                }
              }
              scheduleFlush()
            }
            const browserEvent = parsed.browser_event
            if (browserEvent) {
              browserEventsRef.current.push(browserEvent)
              setBrowserEvents(prev => [...prev, browserEvent])
              // Auto-open browser panel on first browser event
              if (!showBrowser) {
                setShowBrowser(true)
              }
            }
            const browserStatusEvent = parsed.browser_status as BrowserStatus | undefined
            if (browserStatusEvent) {
              browserStatusRef.current = browserStatusEvent
              setBrowserStatus(browserStatusEvent)
            }
            if (parsed.sources && parsed.sources.length > 0) {
              setMessages(prev => {
                const last = prev[prev.length - 1]
                if (last && last.role === 'assistant') {
                  return [...prev.slice(0, -1), { ...last, sources: parsed.sources }]
                }
                return [...prev, { role: 'assistant', content: contentRef.current || '', sources: parsed.sources }]
              })
            }
          } catch {
            // ignore malformed JSON
          }
        }
      }
    } catch (err: any) {
      contentRef.current = `Error: ${err.message || 'Unknown error'}`
      flushToState()
    } finally {
      // Final flush to ensure all content is rendered
      if (rafPending.current) {
        flushToState()
      } else {
        flushToState()
      }
      setBrowserStatus({ state: 'idle' })
      setLoading(false)
      // Clear browser events to stop BrowserPanel polling
      browserEventsRef.current = []
      setBrowserEvents([])
    }
  }

  const handlePaste = async (e: React.ClipboardEvent<HTMLInputElement>) => {
    const items = e.clipboardData.items
    const imageItems: DataTransferItem[] = []

    for (let i = 0; i < items.length; i++) {
      if (items[i].type.startsWith('image/')) {
        imageItems.push(items[i])
      }
    }

    if (imageItems.length > 0) {
      e.preventDefault()
      setUploading(true)
      try {
        const files: File[] = []
        for (const item of imageItems) {
          const blob = item.getAsFile()
          if (blob) {
            files.push(blob)
          }
        }
        if (files.length > 0) {
          const dt = new DataTransfer()
          files.forEach(f => dt.items.add(f))
          await handleUpload(dt.files)
        }
      } finally {
        setUploading(false)
      }
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50" onClick={onClose}>
      <div
        className={`relative bg-white rounded-xl w-full shadow-xl flex overflow-hidden ${showBrowser ? 'max-w-6xl h-[85vh]' : 'max-w-lg h-[80vh]'}`}
        onClick={e => e.stopPropagation()}
      >
        {/* Main chat area */}
        <div className={`flex flex-col overflow-hidden ${showBrowser ? 'w-[55%]' : 'w-full'}`}>
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-200">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-full bg-gray-900 text-white flex items-center justify-center">
              <Bot size={18} />
            </div>
            <div>
              <h3 className="font-semibold text-gray-900 text-sm">{agent.name}</h3>
              <p className="text-xs text-gray-500">{agent.model || 'kimi-latest'}</p>
            </div>
          </div>
          <div className="flex items-center gap-1">
            <button
              onClick={() => setShowSummaryPanel(v => !v)}
              className="p-1.5 hover:bg-gray-100 rounded-lg text-gray-500"
              title="摘要库"
            >
              <BookOpen size={18} />
            </button>
            {agent.config?.enable_browsing && (
              <button
                onClick={() => setShowBrowser(v => !v)}
                className={`p-1.5 rounded-lg flex items-center gap-1 text-xs ${showBrowser ? 'bg-blue-100 text-blue-700' : 'hover:bg-gray-100 text-gray-500'}`}
                title="浏览器面板"
              >
                <Globe size={16} />
                {showBrowser && <span>浏览器</span>}
              </button>
            )}
            <button onClick={onClose} className="p-1.5 hover:bg-gray-100 rounded-lg text-gray-500">
              <X size={18} />
            </button>
          </div>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-gray-200">
          <button
            onClick={() => setActiveTab('chat')}
            className={`flex-1 py-2 text-xs font-medium transition-colors ${
              activeTab === 'chat'
                ? 'text-gray-900 border-b-2 border-gray-900 bg-gray-50'
                : 'text-gray-500 hover:text-gray-700 hover:bg-gray-50'
            }`}
          >
            💬 Web 聊天
          </button>
          {agent.config?.feishu?.enabled && (
            <button
              onClick={() => setActiveTab('feishu')}
              className={`flex-1 py-2 text-xs font-medium transition-colors ${
                activeTab === 'feishu'
                  ? 'text-indigo-700 border-b-2 border-indigo-600 bg-indigo-50'
                  : 'text-gray-500 hover:text-gray-700 hover:bg-gray-50'
              }`}
            >
              🤖 飞书历史
            </button>
          )}
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
          {activeTab === 'chat' && historyLoading && (
            <div className="flex justify-center mt-10">
              <span className="inline-block w-5 h-5 border-2 border-gray-300 border-t-gray-600 rounded-full animate-spin" />
            </div>
          )}
          {activeTab === 'feishu' && feishuHistoryLoading && (
            <div className="flex justify-center mt-10">
              <span className="inline-block w-5 h-5 border-2 border-gray-300 border-t-gray-600 rounded-full animate-spin" />
            </div>
          )}
          {activeTab === 'chat' && !historyLoading && messages.length === 0 && (
            <div className="text-center text-gray-400 text-sm mt-10">Start a conversation with {agent.name}</div>
          )}
          {activeTab === 'feishu' && !feishuHistoryLoading && (!feishuHistoryData?.messages || feishuHistoryData.messages.length === 0) && (
            <div className="text-center text-gray-400 text-sm mt-10">暂无飞书聊天记录</div>
          )}

          {activeTab === 'chat' && messages.map((msg, idx) => (
            <div key={idx} className={`group flex gap-2 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              {msg.role === 'assistant' && (
                <div className="w-7 h-7 rounded-full bg-gray-900 text-white flex items-center justify-center flex-shrink-0 mt-1">
                  <Bot size={14} />
                </div>
              )}
              <div className="max-w-[80%]">
                {msg.role === 'assistant' && msg.reasoning && (
                  <div className="mb-1.5 p-2 bg-amber-50 border border-amber-200 rounded-lg text-xs text-amber-800 max-w-full">
                    <div className="font-medium mb-0.5 flex items-center gap-1">
                      <span>🧠</span> 思考过程
                    </div>
                    <div className="whitespace-pre-wrap opacity-80">{msg.reasoning}</div>
                  </div>
                )}
                {msg.role === 'assistant' && msg.toolCalls && msg.toolCalls.length > 0 && (
                  <div className="mb-1.5 flex flex-wrap gap-1">
                    {msg.toolCalls.map((tc, i) => (
                      <span key={i} className="text-[10px] bg-blue-100 text-blue-700 px-1.5 py-0.5 rounded">🔧 {tc}</span>
                    ))}
                  </div>
                )}
                {msg.role === 'assistant' && loading && idx === messages.length - 1 && browserStatus.state !== 'idle' && (
                  <div className="mb-1.5 flex items-center gap-2 text-xs text-blue-600 animate-pulse">
                    <Globe size={14} className="animate-spin" />
                    <span>
                      {browserStatus.state === 'navigating' && browserStatus.url
                        ? `🌐 正在打开网页: ${browserStatus.url.slice(0, 40)}...`
                        : browserStatus.state === 'reading'
                        ? '🌐 正在读取网页内容...'
                        : '🌐 正在浏览网页...'}
                    </span>
                  </div>
                )}
                <div
                  className={`px-4 py-2 rounded-2xl text-sm leading-relaxed ${
                    msg.role === 'user'
                      ? 'bg-gray-900 text-white rounded-br-md'
                      : 'bg-gray-100 text-gray-900 rounded-bl-md'
                  }`}
                >
                  {msg.content || (msg.role === 'assistant' && loading && idx === messages.length - 1 ? (
                    <span className="inline-block w-4 h-4 border-2 border-gray-300 border-t-gray-600 rounded-full animate-spin" />
                  ) : null)}
                </div>
                {msg.role === 'user' && msg.fileIds && msg.fileIds.length > 0 && (
                  <div className="flex flex-wrap gap-1 mt-1 justify-end">
                    {msg.fileIds.map((fid) => (
                      <img
                        key={fid}
                        src={`/api/agents/${agent.id}/files/${fid}`}
                        alt="attachment"
                        className="w-16 h-16 object-cover rounded-lg border border-gray-200"
                      />
                    ))}
                  </div>
                )}
                {msg.role === 'assistant' && msg.sources && msg.sources.length > 0 && (
                  <div className="mt-1.5">
                    <details className="text-xs">
                      <summary className="cursor-pointer text-gray-500 hover:text-gray-700 flex items-center gap-1">
                        <span>🔗</span>
                        <span>数据来源 ({msg.sources.length})</span>
                      </summary>
                      <div className="mt-1 space-y-1 pl-4 border-l-2 border-gray-200">
                        {msg.sources.map((source, i) => (
                          <div key={i} className="flex items-start gap-1">
                            <span className="text-gray-400 mt-0.5">
                              {source.type === 'search' ? '🔍' : '🌐'}
                            </span>
                            <a
                              href={source.url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-blue-600 hover:text-blue-800 hover:underline truncate max-w-[200px]"
                              title={source.title || source.url}
                            >
                              {source.title || getDomain(source.url)}
                            </a>
                          </div>
                        ))}
                      </div>
                    </details>
                  </div>
                )}
                {msg.content && !loading && (
                  <button
                    onClick={() => handleCopy(msg.content, idx)}
                    className={`flex items-center gap-1 mt-1 text-[10px] text-gray-400 hover:text-gray-600 opacity-0 group-hover:opacity-100 transition-opacity ${msg.role === 'user' ? 'justify-end ml-auto' : ''}`}
                  >
                    {copiedIdx === idx ? <Check size={10} /> : <Copy size={10} />}
                    {copiedIdx === idx ? '已复制' : '复制'}
                  </button>
                )}
                {msg.role === 'user' && msg.fileIds && msg.fileIds.length > 0 && (
                  <div className="flex items-center gap-1 mt-1 justify-end">
                    <FileText size={10} className="text-gray-400" />
                    <span className="text-[10px] text-gray-400">
                      {msg.fileIds.length} 个附件
                    </span>
                  </div>
                )}
              </div>
              {msg.role === 'user' && (
                <div className="w-7 h-7 rounded-full bg-gray-200 text-gray-700 flex items-center justify-center flex-shrink-0 mt-1">
                  <User size={14} />
                </div>
              )}
            </div>
          ))}

          {activeTab === 'feishu' && feishuHistoryData?.messages?.map((msg: any, idx: number) => (
            <div key={idx} className={`flex gap-2 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              {msg.role === 'assistant' && (
                <div className="w-7 h-7 rounded-full bg-indigo-600 text-white flex items-center justify-center flex-shrink-0 mt-1">
                  <MessageCircle size={14} />
                </div>
              )}
              <div className="max-w-[80%]">
                <div
                  className={`px-4 py-2 rounded-2xl text-sm leading-relaxed ${
                    msg.role === 'user'
                      ? 'bg-indigo-100 text-indigo-900 rounded-br-md'
                      : 'bg-gray-100 text-gray-900 rounded-bl-md'
                  }`}
                >
                  {msg.content}
                </div>
                {msg.timestamp && (
                  <div className="text-[10px] text-gray-400 mt-0.5 text-right">
                    {new Date(msg.timestamp).toLocaleString()}
                  </div>
                )}
              </div>
              {msg.role === 'user' && (
                <div className="w-7 h-7 rounded-full bg-indigo-200 text-indigo-700 flex items-center justify-center flex-shrink-0 mt-1">
                  <User size={14} />
                </div>
              )}
            </div>
          ))}

          <div ref={bottomRef} />
        </div>

        {showSummaryPanel && (
          <div className="absolute right-0 top-[57px] bottom-[140px] w-64 bg-white border-l border-gray-200 shadow-lg z-10 overflow-y-auto">
            <div className="p-3 border-b border-gray-100 flex items-center justify-between">
              <h4 className="text-xs font-semibold text-gray-700">📚 历史摘要</h4>
              <button onClick={() => setShowSummaryPanel(false)} className="text-gray-400 hover:text-gray-600">
                <X size={14} />
              </button>
            </div>
            <div className="p-2 space-y-2">
              {summariesData?.items?.map(s => (
                <div key={s.id} className="bg-gray-50 rounded-lg p-2 text-xs border border-gray-100">
                  <div className="flex items-center gap-1.5 mb-1">
                    <input
                      type="checkbox"
                      checked={selectedSummaries.includes(s.id)}
                      onChange={e => {
                        if (e.target.checked) {
                          setSelectedSummaries(prev => [...prev, s.id])
                        } else {
                          setSelectedSummaries(prev => prev.filter(id => id !== s.id))
                        }
                      }}
                      className="rounded"
                    />
                    <span className="font-medium text-gray-800 truncate">{s.file_name}</span>
                  </div>
                  <p className="text-gray-500 line-clamp-3">{s.summary}</p>
                  <div className="text-[10px] text-gray-400 mt-1">
                    {new Date(s.created_at).toLocaleDateString()} · {s.summary_char_count} 字
                  </div>
                </div>
              ))}
              {!summariesData?.items?.length && (
                <div className="text-center text-gray-400 text-xs py-4">暂无历史摘要</div>
              )}
            </div>
          </div>
        )}

        {activeTab === 'chat' && (
          <>
            <ChatFileBar
              files={files}
              fileMode={fileMode}
              onUpload={handleUpload}
              onRemove={handleRemoveFile}
              onModeChange={handleModeChange}
              disabled={loading}
              uploading={uploading}
              agentId={agent.id}
            />
            <div className="px-5 py-4 border-t border-gray-200">
              <div className="flex gap-2">
                <input
                  type="text"
                  className="flex-1 border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-gray-900"
                  placeholder="Type a message..."
                  value={input}
                  onChange={e => setInput(e.target.value)}
                  onKeyDown={handleKeyDown}
                  onPaste={handlePaste}
                  disabled={loading}
                />
                <button
                  onClick={handleSend}
                  disabled={loading || !input.trim()}
                  className="px-4 py-2 bg-gray-900 text-white rounded-lg text-sm hover:bg-gray-800 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-1"
                >
                  <Send size={14} />
                </button>
              </div>
            </div>
          </>
        )}
      </div>

      {/* Browser panel */}
      {showBrowser && agent.config?.enable_browsing && (
        <div className="w-[45%] border-l border-gray-200">
          <BrowserPanel
            agentId={agent.id}
            browserEvents={browserEvents}
            onClose={() => setShowBrowser(false)}
          />
        </div>
      )}
    </div>
  </div>
  )
}
