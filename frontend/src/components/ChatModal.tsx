import { useState, useRef, useEffect, useCallback } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Bot, User, Send, X, FileText } from 'lucide-react'
import type { Agent, ChatFile } from '../types'
import { chatApi, fileApi } from '../api/client'
import ChatFileBar, { type FileMode } from './ChatFileBar'

interface Message {
  role: 'user' | 'assistant'
  content: string
  fileIds?: string[]
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

  const { data: historyData, isLoading: historyLoading } = useQuery({
    queryKey: ['chat_history', agent.id],
    queryFn: () => chatApi.history(agent.id),
    enabled: !!agent.id,
  })

  // Load existing files
  const { data: filesData } = useQuery({
    queryKey: ['chat_files', agent.id],
    queryFn: () => fileApi.listAgent(agent.id),
    enabled: !!agent.id,
  })

  useEffect(() => {
    if (filesData?.files) {
      setFiles(filesData.files)
    }
  }, [filesData])

  useEffect(() => {
    if (historyData?.messages) {
      setMessages(historyData.messages.map(m => ({
        role: m.role as 'user' | 'assistant',
        content: m.content,
      })))
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

  const handleSend = async () => {
    const text = input.trim()
    if (!text || loading) return

    const activeFileIds = files.map(f => f.id)

    setInput('')
    setMessages(prev => [...prev, { role: 'user', content: text, fileIds: activeFileIds }])
    setLoading(true)

    // Add placeholder assistant message
    setMessages(prev => [...prev, { role: 'assistant', content: '' }])

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
            const parsed = JSON.parse(data) as { content?: string }
            const chunk = parsed.content || ''
            setMessages(prev => {
              const last = prev[prev.length - 1]
              if (last && last.role === 'assistant') {
                return [
                  ...prev.slice(0, -1),
                  { ...last, content: last.content + chunk }
                ]
              }
              return prev
            })
          } catch {
            // ignore malformed JSON
          }
        }
      }
    } catch (err: any) {
      setMessages(prev => {
        const next = [...prev]
        next[next.length - 1] = { role: 'assistant', content: `Error: ${err.message || 'Unknown error'}` }
        return next
      })
    } finally {
      setLoading(false)
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
        className="bg-white rounded-xl w-full max-w-lg h-[80vh] shadow-xl flex flex-col overflow-hidden"
        onClick={e => e.stopPropagation()}
      >
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
          <button onClick={onClose} className="p-1.5 hover:bg-gray-100 rounded-lg text-gray-500">
            <X size={18} />
          </button>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
          {historyLoading && (
            <div className="flex justify-center mt-10">
              <span className="inline-block w-5 h-5 border-2 border-gray-300 border-t-gray-600 rounded-full animate-spin" />
            </div>
          )}
          {!historyLoading && messages.length === 0 && (
            <div className="text-center text-gray-400 text-sm mt-10">Start a conversation with {agent.name}</div>
          )}
          {messages.map((msg, idx) => (
            <div key={idx} className={`flex gap-2 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              {msg.role === 'assistant' && (
                <div className="w-7 h-7 rounded-full bg-gray-900 text-white flex items-center justify-center flex-shrink-0 mt-1">
                  <Bot size={14} />
                </div>
              )}
              <div className="max-w-[80%]">
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
                {/* File attachments indicator for user messages */}
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
          {/* Pending hint */}
          {!loading && messages.length > 0 && messages[messages.length - 1].role === 'user' && (
            <div className="flex justify-start">
              <div className="bg-yellow-50 border border-yellow-200 text-yellow-800 px-3 py-2 rounded-lg text-xs">
                Agent 正在回答中，关闭弹窗也不会中断。请稍后再打开查看完整结果。
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>

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
