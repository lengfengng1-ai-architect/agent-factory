import type { Agent } from '../types'
import { Bot, MessageSquare, Pencil, Trash2 } from 'lucide-react'

interface Props {
  agent: Agent
  onEdit: (agent: Agent) => void
  onDelete: (id: number) => void
  onChat: (agent: Agent) => void
}

export default function AgentCard({ agent, onEdit, onDelete, onChat }: Props) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm hover:shadow-md transition-shadow">
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-full bg-gray-900 text-white flex items-center justify-center">
            <Bot size={20} />
          </div>
          <div>
            <h3 className="font-semibold text-gray-900">{agent.name}</h3>
            <p className="text-sm text-gray-500 line-clamp-1">{agent.description}</p>
            {agent.config?.feishu?.enabled && (
              <span className="inline-flex items-center gap-1 text-[10px] bg-blue-50 text-blue-600 px-1.5 py-0.5 rounded-full">
                <span className="w-1.5 h-1.5 rounded-full bg-blue-500"></span>
                飞书
              </span>
            )}
          </div>
        </div>
        <div className="flex gap-1">
          <button onClick={() => onChat(agent)} className="p-1.5 hover:bg-blue-50 text-blue-600 rounded-lg" title="Chat">
            <MessageSquare size={16} />
          </button>
          <button onClick={() => onEdit(agent)} className="p-1.5 hover:bg-gray-100 rounded-lg" title="Edit">
            <Pencil size={16} />
          </button>
          <button onClick={() => onDelete(agent.id)} className="p-1.5 hover:bg-red-50 text-red-600 rounded-lg" title="Delete">
            <Trash2 size={16} />
          </button>
        </div>
      </div>
      <div className="mt-3 text-xs text-gray-400">ID: {agent.id}</div>
    </div>
  )
}
