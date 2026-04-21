import type { Agent } from '../types'
import { Bot, Pencil, Trash2 } from 'lucide-react'

interface Props {
  agent: Agent
  onEdit: (agent: Agent) => void
  onDelete: (id: number) => void
}

export default function AgentCard({ agent, onEdit, onDelete }: Props) {
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
          </div>
        </div>
        <div className="flex gap-1">
          <button onClick={() => onEdit(agent)} className="p-1.5 hover:bg-gray-100 rounded-lg"><Pencil size={16} /></button>
          <button onClick={() => onDelete(agent.id)} className="p-1.5 hover:bg-red-50 text-red-600 rounded-lg"><Trash2 size={16} /></button>
        </div>
      </div>
      <div className="mt-3 text-xs text-gray-400">ID: {agent.id}</div>
    </div>
  )
}
