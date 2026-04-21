import { useState, useRef, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Bot, Send, X, Users } from 'lucide-react'
import { agentApi, groupChatApi } from '../api/client'
import type { Group } from '../types'

interface GroupMessage {
  role: 'user' | 'assistant'
  agent_id: number
  agent_name: string
  content: string
  timestamp?: string
  done?: boolean
  phase?: 'expert' | 'moderator'
  round?: number
}

interface Props {
  group: Group
  onClose: () => void
}

export default function GroupChatModal({ group, onClose }: Props) {
  const [messages, setMessages] = useState<GroupMessage[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  const { data: agents } = useQuery({ queryKey: ['agents'], queryFn: agentApi.list })
  const groupAgents = agents?.filter(a => group.agent_ids?.includes(a.id)) || []

  const { data: historyData, isLoading: historyLoading } = useQuery({
    queryKey: ['group_chat_history', group.id],
    queryFn: () => groupChatApi.history(group.id),
    enabled: !!group.id,
  })

  useEffect(() => {
    if (historyData?.messages) {
      setMessages(historyData.messages.map((m: any) => ({
        role: m.role as 'user' | 'assistant',
        agent_id: m.agent_id || 0,
        agent_name: m.agent_name || 'Agent',
        content: m.content,
        timestamp: m.timestamp,
      })))
    }
  }, [historyData])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const updateAgentMessage = (agentId: number, content: string) => {
    setMessages(prev => {
      const idx = prev.findIndex(m => m.agent_id === agentId && m.role === 'assistant' && !m.done)
      if (idx >= 0) {
        const next = [...prev]
        next[idx] = { ...next[idx], content }
        return next
      }
      return prev
    })
  }

  const handleParallelChat = async (text: string) => {
    // Add placeholder messages for each agent
    const agentPlaceholders = groupAgents.map(a => ({
      role: 'assistant' as const,
      agent_id: a.id,
      agent_name: a.name,
      content: '',
    }))
    setMessages(prev => [...prev, ...agentPlaceholders])

    // Call each agent in parallel
    const promises = groupAgents.map(async (agent) => {
      try {
        const res = await fetch(`/api/agents/${agent.id}/chat`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ message: text, group_id: group.id }),
        })

        if (!res.ok || !res.body) {
          updateAgentMessage(agent.id, `Error: ${res.statusText}`)
          return
        }

        const reader = res.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''
        let fullContent = ''

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
              const parsed = JSON.parse(data) as { content?: string }
              const chunk = parsed.content || ''
              fullContent += chunk
              updateAgentMessage(agent.id, fullContent)
            } catch {
              // ignore
            }
          }
        }
      } catch (err: any) {
        updateAgentMessage(agent.id, `Error: ${err.message}`)
      }
    })

    await Promise.all(promises)
  }

  const handleGroupStream = async (text: string) => {
    // Add a single placeholder for the stream
    setMessages(prev => [...prev, { role: 'assistant', agent_id: -1, agent_name: 'Loading...', content: '' }])

    try {
      const res = await fetch(`/api/groups/${group.id}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text }),
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
            const parsed = JSON.parse(data) as { agent_id: number; agent_name: string; content: string; done: boolean; phase?: string; round?: number }

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

  const handleSend = async () => {
    const text = input.trim()
    if (!text || loading) return

    setInput('')
    setMessages(prev => [...prev, { role: 'user', agent_id: 0, agent_name: 'User', content: text }])
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
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50" onClick={onClose}>
      <div className={`bg-white rounded-xl shadow-xl flex flex-col overflow-hidden ${isParallel ? 'w-full max-w-4xl h-[85vh]' : 'w-full max-w-lg h-[80vh]'}`} onClick={e => e.stopPropagation()}>
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
          <button onClick={onClose} className="p-1.5 hover:bg-gray-100 rounded-lg text-gray-500">
            <X size={18} />
          </button>
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
              <div key={idx}>
                {msg.role === 'user' ? (
                  <div className="flex justify-end">
                    <div className="max-w-[80%] px-4 py-2 rounded-2xl bg-gray-900 text-white text-sm rounded-br-md">
                      {msg.content}
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
                        {chatType === 'debate' && msg.agent_id >= 0 && (
                          ` · ${msg.agent_id === groupAgents[0]?.id ? '正方' : '反方'}`
                        )}
                      </div>
                      <div className="px-4 py-2 rounded-2xl bg-gray-100 text-gray-900 text-sm rounded-bl-md whitespace-pre-wrap">
                        {msg.content || (loading && idx === messages.length - 1 ? (
                          <span className="inline-block w-4 h-4 border-2 border-gray-300 border-t-gray-600 rounded-full animate-spin" />
                        ) : null)}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            ))}
            <div ref={bottomRef} />
          </div>
        )}

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
