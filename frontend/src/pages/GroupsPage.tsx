import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Users, Pencil, Trash2, MessageCircle } from 'lucide-react'
import { groupApi, agentApi } from '../api/client'
import type { Group } from '../types'
import GroupModal from '../components/GroupModal'
import GroupChatModal from '../components/GroupChatModal'

export default function GroupsPage() {
  const [modalOpen, setModalOpen] = useState(false)
  const [editing, setEditing] = useState<Group | null>(null)
  const [chatGroup, setChatGroup] = useState<Group | null>(null)
  const qc = useQueryClient()

  const { data: groups = [] } = useQuery({ queryKey: ['groups'], queryFn: groupApi.list })
  const { data: agents = [] } = useQuery({ queryKey: ['agents'], queryFn: agentApi.list })

  const create = useMutation({ mutationFn: groupApi.create, onSuccess: () => qc.invalidateQueries({ queryKey: ['groups'] }) })
  const update = useMutation({ mutationFn: ({ id, data }: { id: number; data: Partial<Group> }) => groupApi.update(id, data), onSuccess: () => qc.invalidateQueries({ queryKey: ['groups'] }) })
  const remove = useMutation({ mutationFn: groupApi.delete, onSuccess: () => qc.invalidateQueries({ queryKey: ['groups'] }) })

  const agentMap = new Map(agents.map(a => [a.id, a.name]))

  const handleSave = (data: { name: string; description: string; agent_ids: number[]; chat_type: string; config?: Record<string, any> }) => {
    if (editing) update.mutate({ id: editing.id, data })
    else create.mutate(data)
  }

  const handleChat = (group: Group) => {
    setChatGroup(group)
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-2xl font-bold">Groups</h2>
        <button onClick={() => { setEditing(null); setModalOpen(true) }} className="flex items-center gap-2 px-4 py-2 bg-gray-900 text-white rounded-lg text-sm hover:bg-gray-800">
          <Plus size={16} /> New Group
        </button>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {groups.map(g => (
          <div key={g.id} className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
            <div className="flex items-start justify-between">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-full bg-blue-600 text-white flex items-center justify-center">
                  <Users size={20} />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="font-semibold text-gray-900">{g.name}</h3>
                    <span className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded-full border border-gray-200">
                      {g.chat_type === 'parallel' && '并行咨询'}
                      {g.chat_type === 'brainstorm' && '头脑风暴'}
                      {g.chat_type === 'debate' && '辩论'}
                      {g.chat_type === 'moderator' && '主持人'}
                      {!g.chat_type && '并行咨询'}
                    </span>
                  </div>
                  <p className="text-sm text-gray-500">{g.description}</p>
                </div>
              </div>
              <div className="flex gap-1">
                <button onClick={() => handleChat(g)} className="p-1.5 hover:bg-indigo-50 text-indigo-600 rounded-lg" title="Chat">
                  <MessageCircle size={16} />
                </button>
                <button onClick={() => { setEditing(g); setModalOpen(true) }} className="p-1.5 hover:bg-gray-100 rounded-lg"><Pencil size={16} /></button>
                <button onClick={() => remove.mutate(g.id)} className="p-1.5 hover:bg-red-50 text-red-600 rounded-lg"><Trash2 size={16} /></button>
              </div>
            </div>
            <div className="mt-3">
              <p className="text-xs font-medium text-gray-500 mb-1">Members ({g.agent_ids?.length || 0})</p>
              <div className="flex flex-wrap gap-1">
                {g.agent_ids?.map(id => (
                  <span key={id} className="text-xs bg-gray-100 text-gray-700 px-2 py-0.5 rounded-full">{agentMap.get(id) || `ID:${id}`}</span>
                ))}
              </div>
            </div>
          </div>
        ))}
      </div>
      {modalOpen && <GroupModal group={editing} onClose={() => setModalOpen(false)} onSave={handleSave} />}
      {chatGroup && <GroupChatModal group={chatGroup} onClose={() => setChatGroup(null)} />}
    </div>
  )
}
