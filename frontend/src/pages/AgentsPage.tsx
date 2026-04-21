import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus } from 'lucide-react'
import { agentApi } from '../api/client'
import type { Agent } from '../types'
import AgentCard from '../components/AgentCard'
import AgentModal from '../components/AgentModal'
import ChatModal from '../components/ChatModal'

export default function AgentsPage() {
  const [modalOpen, setModalOpen] = useState(false)
  const [editing, setEditing] = useState<Agent | null>(null)
  const [chatAgent, setChatAgent] = useState<Agent | null>(null)
  const qc = useQueryClient()

  const { data: agents = [], isLoading } = useQuery({ queryKey: ['agents'], queryFn: agentApi.list })

  const create = useMutation({ mutationFn: agentApi.create, onSuccess: () => qc.invalidateQueries({ queryKey: ['agents'] }) })
  const update = useMutation({ mutationFn: ({ id, data }: { id: number; data: Partial<Agent> }) => agentApi.update(id, data), onSuccess: () => qc.invalidateQueries({ queryKey: ['agents'] }) })
  const remove = useMutation({ mutationFn: agentApi.delete, onSuccess: () => qc.invalidateQueries({ queryKey: ['agents'] }) })

  const handleSave = (data: { name: string; description: string; config: Record<string, unknown>; system_prompt: string; model: string; api_url: string; api_key: string; provider: string }) => {
    if (editing) update.mutate({ id: editing.id, data })
    else create.mutate({ ...data, avatar: '' })
  }

  if (isLoading) return <div className="text-gray-500">Loading...</div>

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-2xl font-bold">Agents</h2>
        <button onClick={() => { setEditing(null); setModalOpen(true) }} className="flex items-center gap-2 px-4 py-2 bg-gray-900 text-white rounded-lg text-sm hover:bg-gray-800">
          <Plus size={16} /> New Agent
        </button>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {agents.map(a => (
          <AgentCard
            key={a.id}
            agent={a}
            onEdit={a => { setEditing(a); setModalOpen(true) }}
            onDelete={id => remove.mutate(id)}
            onChat={a => setChatAgent(a)}
          />
        ))}
      </div>
      {modalOpen && <AgentModal agent={editing} onClose={() => setModalOpen(false)} onSave={handleSave} />}
      {chatAgent && <ChatModal agent={chatAgent} onClose={() => setChatAgent(null)} />}
    </div>
  )
}
