import { useState, useRef, useEffect, useCallback } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Bot, Send, X, Users, Maximize2, Minimize2, FileText, BookOpen, Copy, Check } from 'lucide-react'
import { agentApi, groupChatApi, fileApi, summaryApi } from '../api/client'
import type { Group, ChatFile } from '../types'
import ChatFileBar, { type FileMode } from './ChatFileBar'

interface GroupMessage {
  role: 'user' | 'assistant'
  agent_id: number
  agent_name: string
  content: string
  timestamp?: string
  done?: boolean
  phase?: 'expert' | 'moderator'
  round?: number
  fileIds?: string[]
  reasoning?: string
  toolCalls?: string[]
}

interface Props {
  group: Group
  onClose: () => void
}

const STORAGE_KEY = (groupId: number) => `chat_file_mode_group_${groupId}`

export default function GroupChatModal({ group, onClose }: Props) {
  const [messages, setMessages] = useState<GroupMessage[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [isMaximized, setIsMaximized] = useState(false)
  const [files, setFiles] = useState<ChatFile[]>([])
  const [uploading, setUploading] = useState(false)
  const [fileMode, setFileMode] = useState<FileMode>(() => {
    const saved = localStorage.getItem(STORAGE_KEY(group.id))
    return (saved as FileMode) || 'auto'
  })
  const bottomRef = useRef<HTMLDivElement>(null)
  const [showSummaryPanel, setShowSummaryPanel] = useState(false)
  const [selectedSummaries, setSelectedSummaries] = useState<number[]>([])
  const [copiedIdx, setCopiedIdx] = useState<number | null>(null)

  const { data: agents } = useQuery({ queryKey: ['agents'], queryFn: agentApi.list })
  const groupAgents = agents?.filter(a => group.agent_ids?.includes(a.id)) || []

  const { data: historyData, isLoading: historyLoading } = useQuery({
    queryKey: ['group_chat_history', group.id],
    queryFn: () => groupChatApi.history(group.id),
    enabled: !!group.id,
  })

  const { data: filesData } = useQuery({
    queryKey: ['group_chat_files', group.id],
    queryFn: () => fileApi.listGroup(group.id),
    enabled: !!group.id,
  })

  const { data: summariesData } = useQuery({
    queryKey: ['summaries', group.id],
    queryFn: () => summaryApi.list({ group_id: group.id, limit: 20 }),
    enabled: !!group.id && showSummaryPanel,
  })

  useEffect(() => {
    if (filesData?.files) {
      setFiles(filesData.files)
    }
  }, [filesData])

  useEffect(() => {
    if (historyData?.messages) {
      setMessages(historyData.messages.map((m: any) => ({
        role: m.role as 'user' | 'assistant',
        agent_id: m.agent_id || 0,
        agent_name: m.agent_name || 'Agent',
        content: m.content,
        timestamp: m.timestamp,
        done: true,
      })))
    }
  }, [historyData])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleModeChange = useCallback((mode: FileMode) => {
    setFileMode(mode)
    localStorage.setItem(STORAGE_KEY(group.id), mode)
  }, [group.id])

  const handleUpload = useCallback(async (fileList: FileList) => {
    setUploading(true)
    try {
      const res = await fileApi.uploadGroup(group.id, fileList)
      if (res.files) {
        setFiles(prev => [...prev, ...res.files])
      }
    } catch (err: any) {
      alert(`上传失败: ${err.message || 'Unknown error'}`)
    } finally {
      setUploading(false)
    }
  }, [group.id])

  const handleRemoveFile = useCallback(async (fileId: string) => {
    try {
      await fileApi.deleteGroup(group.id, fileId)
      setFiles(prev => prev.filter(f => f.id !== fileId))
    } catch (err: any) {
      alert(`删除失败: ${err.message || 'Unknown error'}`)
    }
  }, [group.id])

  const updateAgentMessage = (agentId: number, content: string, reasoning?: string, toolCalls?: string[]) => {
    setMessages(prev => {
      const idx = prev.findIndex(m => m.agent_id === agentId && m.role === 'assistant' && !m.done)
      if (idx >= 0) {
        const next = [...prev]
        next[idx] = { ...next[idx], content, reasoning, toolCalls }
        return next
      }
      return prev
    })
  }

  const handleParallelChat = async (text: string) => {
    const activeFileIds = files.map(f => f.id)

    // Add placeholder messages for each agent
    const agentPlaceholders = groupAgents.map(a => ({
      role: 'assistant' as const,
      agent_id: a.id,
      agent_name: a.name,
      content: '',
      reasoning: '',
      toolCalls: [] as string[],
    }))
    setMessages(prev => [...prev, ...agentPlaceholders])

    // Call each agent in parallel
    const promises = groupAgents.map(async (agent) => {
      let fullContent = ''
      let fullReasoning = ''
      let toolCalls: string[] = []

      try {
        const res = await fetch(`/api/agents/${agent.id}/chat`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            message: text,
            group_id: group.id,
            files: activeFileIds,
            file_mode: fileMode,
          }),
        })

        if (!res.ok || !res.body) {
          updateAgentMessage(agent.id, `Error: ${res.statusText}`, fullReasoning, toolCalls)
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
              }
              if (parsed.error) {
                fullContent += `\n[Error: ${parsed.error}]`
                updateAgentMessage(agent.id, fullContent, fullReasoning, toolCalls)
                continue
              }
              if (parsed.reasoning) {
                fullReasoning += parsed.reasoning
                updateAgentMessage(agent.id, fullContent, fullReasoning, toolCalls)
              }
              if (parsed.content) {
                fullContent += parsed.content
                updateAgentMessage(agent.id, fullContent, fullReasoning, toolCalls)
              }
              if (parsed.tool_calls && parsed.tool_calls.length > 0) {
                toolCalls = [...toolCalls, ...parsed.tool_calls]
                updateAgentMessage(agent.id, fullContent, fullReasoning, toolCalls)
              }
            } catch {
              // ignore malformed JSON
            }
          }
        }
      } catch (err: any) {
        updateAgentMessage(agent.id, `Error: ${err.message}`, fullReasoning, toolCalls)
      }
    })

    await Promise.all(promises)

    // Mark all pending assistant messages as done
    setMessages(prev => prev.map(m =>
      m.role === 'assistant' && !m.done ? { ...m, done: true } : m
    ))
  }

  const handleGroupStream = async (text: string) => {
    const activeFileIds = files.map(f => f.id)

    // Add a single placeholder for the stream
    setMessages(prev => [...prev, { role: 'assistant', agent_id: -1, agent_name: 'Loading...', content: '' }])

    try {
      const res = await fetch(`/api/groups/${group.id}/chat`, {
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
          const idx = next.findIndex(m => m.agent_id === -1 && m.role === 'assistant')
          if (idx >= 0) next[idx] = { ...next[idx], agent_id: 0, agent_name: 'Error', content: res.statusText }
          return next
        })
        return
      }

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      const agentBuffers: Record<number, string> = {}

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
              agent_id: number
              agent_name: string
              content: string
              done: boolean
              phase?: string
              round?: number
              error?: string
            }

            if (parsed.error) {
              setMessages(prev => {
                const next = [...prev]
                const idx = next.findIndex(m => m.agent_id === parsed.agent_id && m.role === 'assistant' && !m.done)
                if (idx >= 0) {
                  next[idx] = { ...next[idx], content: next[idx].content + `\n[Error: ${parsed.error}]` }
                  return next
                }
                return prev
              })
              continue
            }

            if (parsed.done) {
              // Finalize this agent's message
              setMessages(prev => {
                const idx = prev.findIndex(m => m.agent_id === parsed.agent_id && m.role === 'assistant' && !m.done)
                if (idx >= 0) {
                  const next = [...prev]
                  next[idx] = { ...next[idx], done: true, phase: parsed.phase as 'expert' | 'moderator', round: parsed.round }
                  return next
                }
                return prev
              })
            } else {
              // Accumulate content
              agentBuffers[parsed.agent_id] = (agentBuffers[parsed.agent_id] || '') + parsed.content
              const fullContent = agentBuffers[parsed.agent_id]

              setMessages(prev => {
                const idx = prev.findIndex(m => m.agent_id === parsed.agent_id && m.role === 'assistant' && !m.done)
                if (idx >= 0) {
                  const next = [...prev]
                  next[idx] = { ...next[idx], content: fullContent, agent_name: parsed.agent_name, phase: parsed.phase as 'expert' | 'moderator', round: parsed.round }
                  return next
                } else {
                  return [...prev, { role: 'assistant', agent_id: parsed.agent_id, agent_name: parsed.agent_name, content: fullContent, phase: parsed.phase as 'expert' | 'moderator', round: parsed.round }]
                }
              })
            }
          } catch {
            // ignore malformed JSON
          }
        }
      }
    } catch (err: any) {
      setMessages(prev => {
        const next = [...prev]
        const idx = next.findIndex(m => m.agent_id === -1 && m.role === 'assistant')
        if (idx >= 0) next[idx] = { ...next[idx], agent_id: 0, agent_name: 'Error', content: err.message }
        return next
      })
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
    setMessages(prev => [...prev, { role: 'user', agent_id: 0, agent_name: 'User', content: text, fileIds: activeFileIds }])
    setLoading(true)

    const chatType = group.chat_type || 'parallel'

    if (chatType === 'parallel') {
      await handleParallelChat(text)
    } else {
      await handleGroupStream(text)
    }

    setLoading(false)
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const chatType = group.chat_type || 'parallel'
  const isParallel = chatType === 'parallel'

  return (
    <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center" onClick={onClose}>
      <div className={`bg-white rounded-xl shadow-xl flex flex-col overflow-hidden transition-all duration-200 ${isMaximized ? `w-full h-[calc(100vh-2rem)] ${isParallel ? 'max-w-6xl' : 'max-w-3xl'}` : `${isParallel ? 'w-full max-w-4xl h-[85vh]' : 'w-full max-w-lg h-[80vh]'}`}`} onClick={e => e.stopPropagation()}>
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-200">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-full bg-indigo-600 text-white flex items-center justify-center">
              <Users size={18} />
            </div>
            <div>
              <h3 className="font-semibold text-gray-900 text-sm">{group.name}</h3>
              <div className="flex items-center gap-2">
                <span className="text-xs text-gray-500">{groupAgents.length} agents</span>
                <span className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded-full">
                  {chatType === 'parallel' && '并行咨询'}
                  {chatType === 'brainstorm' && '头脑风暴'}
                  {chatType === 'debate' && '辩论'}
                  {chatType === 'moderator' && '主持人'}
                </span>
              </div>
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
            <button onClick={() => setIsMaximized(v => !v)} className="p-1.5 hover:bg-gray-100 rounded-lg text-gray-500" title={isMaximized ? 'Minimize' : 'Maximize'}>
              {isMaximized ? <Minimize2 size={18} /> : <Maximize2 size={18} />}
            </button>
            <button onClick={onClose} className="p-1.5 hover:bg-gray-100 rounded-lg text-gray-500">
              <X size={18} />
            </button>
          </div>
        </div>

        {/* Agent avatars */}
        <div className="px-5 py-2 border-b border-gray-100 flex gap-2 overflow-x-auto">
          {groupAgents.map(a => (
            <div key={a.id} className="flex items-center gap-1.5 bg-gray-50 px-2 py-1 rounded-full text-xs text-gray-700">
              <Bot size={12} />
              {a.name}
            </div>
          ))}
        </div>

        {/* Messages */}
        {isParallel ? (
          <div className="flex-1 overflow-y-auto p-4 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {historyLoading && (
              <div className="col-span-full flex justify-center mt-10">
                <span className="inline-block w-5 h-5 border-2 border-gray-300 border-t-gray-600 rounded-full animate-spin" />
              </div>
            )}
            {!historyLoading && messages.length === 0 && (
              <div className="col-span-full text-center text-gray-400 text-sm mt-10">Start a group conversation</div>
            )}
            {groupAgents.map(agent => {
              const agentMsgs = messages.filter(m => m.agent_id === agent.id && m.role === 'assistant')
              const latestMsg = agentMsgs[agentMsgs.length - 1]
              return (
                <div key={agent.id} className="bg-gray-50 rounded-xl p-4 border border-gray-200">
                  <div className="flex items-center gap-2 mb-3">
                    <div className="w-6 h-6 rounded-full bg-gray-900 text-white flex items-center justify-center">
                      <Bot size={12} />
                    </div>
                    <span className="text-sm font-medium text-gray-900">{agent.name}</span>
                  </div>
                  <div className="text-sm text-gray-700 whitespace-pre-wrap min-h-[3rem]">
                    {latestMsg?.reasoning && (
                      <div className="mb-2 p-2 bg-amber-50 border border-amber-200 rounded text-xs text-amber-800">
                        <div className="font-medium mb-1 flex items-center gap-1">
                          <span>🧠</span> 思考过程
                        </div>
                        <div className="whitespace-pre-wrap opacity-80">{latestMsg.reasoning}</div>
                      </div>
                    )}
                    {latestMsg?.toolCalls && latestMsg.toolCalls.length > 0 && (
                      <div className="mb-2 flex flex-wrap gap-1">
                        {latestMsg.toolCalls.map((tc, i) => (
                          <span key={i} className="text-[10px] bg-blue-100 text-blue-700 px-1.5 py-0.5 rounded">🔧 {tc}</span>
                        ))}
                      </div>
                    )}
                    {latestMsg?.content || (loading ? (
                      <span className="inline-block w-4 h-4 border-2 border-gray-300 border-t-gray-600 rounded-full animate-spin" />
                    ) : 'Waiting...')}
                  </div>
                </div>
              )
            })}
          </div>
        ) : (
          <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
            {historyLoading && (
              <div className="flex justify-center mt-10">
                <span className="inline-block w-5 h-5 border-2 border-gray-300 border-t-gray-600 rounded-full animate-spin" />
              </div>
            )}
            {!historyLoading && messages.length === 0 && (
              <div className="text-center text-gray-400 text-sm mt-10">Start a group conversation</div>
            )}
            {messages.map((msg, idx) => (
              <div key={idx} className="group">
                {msg.role === 'user' ? (
                  <div className="flex justify-end">
                    <div className="max-w-[80%]">
                      <div className="max-w-[80%] px-4 py-2 rounded-2xl bg-gray-900 text-white text-sm rounded-br-md">
                        {msg.content}
                      </div>
                      {msg.content && !loading && (
                        <button
                          onClick={() => handleCopy(msg.content, idx)}
                          className="flex items-center gap-1 mt-1 text-[10px] text-gray-400 hover:text-gray-600 opacity-0 group-hover:opacity-100 transition-opacity ml-auto"
                        >
                          {copiedIdx === idx ? <Check size={10} /> : <Copy size={10} />}
                          {copiedIdx === idx ? '已复制' : '复制'}
                        </button>
                      )}
                      {msg.fileIds && msg.fileIds.length > 0 && (
                        <div className="flex items-center gap-1 mt-1 justify-end">
                          <FileText size={10} className="text-gray-400" />
                          <span className="text-[10px] text-gray-400">{msg.fileIds.length} 个附件</span>
                        </div>
                      )}
                    </div>
                  </div>
                ) : (
                  <div className="flex gap-2">
                    <div className="w-7 h-7 rounded-full bg-gray-900 text-white flex items-center justify-center flex-shrink-0 mt-1">
                      <Bot size={14} />
                    </div>
                    <div className="max-w-[80%]">
                      <div className="text-xs text-gray-500 mb-0.5">
                        {msg.agent_name}
                        {msg.phase && ` · ${msg.phase === 'expert' ? '专家' : '主持人'}`}
                        {msg.round && ` · Round ${msg.round}`}
                      </div>
                      {msg.reasoning && (
                        <div className="mb-1.5 p-2 bg-amber-50 border border-amber-200 rounded-lg text-xs text-amber-800 max-w-full">
                          <div className="font-medium mb-0.5 flex items-center gap-1">
                            <span>🧠</span> 思考过程
                          </div>
                          <div className="whitespace-pre-wrap opacity-80">{msg.reasoning}</div>
                        </div>
                      )}
                      {msg.toolCalls && msg.toolCalls.length > 0 && (
                        <div className="mb-1.5 flex flex-wrap gap-1">
                          {msg.toolCalls.map((tc, i) => (
                            <span key={i} className="text-[10px] bg-blue-100 text-blue-700 px-1.5 py-0.5 rounded">🔧 {tc}</span>
                          ))}
                        </div>
                      )}
                      <div className="px-4 py-2 rounded-2xl bg-gray-100 text-gray-900 text-sm rounded-bl-md whitespace-pre-wrap">
                        {msg.content || (loading && idx === messages.length - 1 ? (
                          <span className="inline-block w-4 h-4 border-2 border-gray-300 border-t-gray-600 rounded-full animate-spin" />
                        ) : null)}
                      </div>
                      {msg.content && !loading && (
                        <button
                          onClick={() => handleCopy(msg.content, idx)}
                          className="flex items-center gap-1 mt-1 text-[10px] text-gray-400 hover:text-gray-600 opacity-0 group-hover:opacity-100 transition-opacity"
                        >
                          {copiedIdx === idx ? <Check size={10} /> : <Copy size={10} />}
                          {copiedIdx === idx ? '已复制' : '复制'}
                        </button>
                      )}
                    </div>
                  </div>
                )}
              </div>
            ))}
            <div ref={bottomRef} />
          </div>
        )}

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

        {/* File bar */}
        <ChatFileBar
          files={files}
          fileMode={fileMode}
          onUpload={handleUpload}
          onRemove={handleRemoveFile}
          onModeChange={handleModeChange}
          disabled={loading}
          uploading={uploading}
        />

        {/* Input */}
        <div className="px-5 py-4 border-t border-gray-200">
          <div className="flex gap-2">
            <input
              type="text"
              className="flex-1 border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-gray-900"
              placeholder="Type a message..."
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
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
      </div>
    </div>
  )
}
