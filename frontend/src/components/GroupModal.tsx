import { useState, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import type { Group } from '../types'
import { agentApi } from '../api/client'

interface Props {
  group?: Group | null
  onClose: () => void
  onSave: (data: { name: string; description: string; agent_ids: number[]; chat_type: string }) => void
}

export default function GroupModal({ group, onClose, onSave }: Props) {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [selectedAgentIds, setSelectedAgentIds] = useState<number[]>([])
  const [chatType, setChatType] = useState('parallel')

  const { data: agents = [] } = useQuery({ queryKey: ['agents'], queryFn: agentApi.list })

  useEffect(() => {
    if (group) {
      setName(group.name)
      setDescription(group.description)
      setSelectedAgentIds(group.agent_ids || [])
      setChatType(group.chat_type || 'parallel')
    } else {
      setName('')
      setDescription('')
      setSelectedAgentIds([])
      setChatType('parallel')
    }
  }, [group])

  const toggleAgent = (id: number) => {
    setSelectedAgentIds(prev =>
      prev.includes(id) ? prev.filter(i => i !== id) : [...prev, id]
    )
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    onSave({ name, description, agent_ids: selectedAgentIds, chat_type: chatType })
    onClose()
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50" onClick={onClose}>
      <div className="bg-white rounded-xl p-6 w-full max-w-md shadow-xl max-h-[90vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
        <h2 className="text-lg font-bold mb-4">{group ? 'Edit Group' : 'New Group'}</h2>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700">Name</label>
            <input className="mt-1 w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" value={name} onChange={e => setName(e.target.value)} required />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700">Description</label>
            <textarea className="mt-1 w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" rows={3} value={description} onChange={e => setDescription(e.target.value)} />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">Chat Mode</label>
            <div className="space-y-2">
              {[
                { key: 'parallel', label: '并行咨询', desc: '所有 Agent 同时回答，快速收集多方意见' },
                { key: 'brainstorm', label: '头脑风暴', desc: 'Agent 依次发言，互相激发创意' },
                { key: 'debate', label: '辩论模式', desc: '两个 Agent 正反方对抗讨论' },
                { key: 'moderator', label: '主持人模式', desc: '主持人 Agent 分派问题并汇总' },
              ].map(opt => (
                <label key={opt.key} className={`flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${chatType === opt.key ? 'border-gray-900 bg-gray-50' : 'border-gray-200 hover:border-gray-300'}`}>
                  <input
                    type="radio"
                    name="chat_type"
                    value={opt.key}
                    checked={chatType === opt.key}
                    onChange={() => setChatType(opt.key)}
                    className="mt-1"
                  />
                  <div>
                    <div className="text-sm font-medium text-gray-900">{opt.label}</div>
                    <div className="text-xs text-gray-500">{opt.desc}</div>
                  </div>
                </label>
              ))}
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">Agents</label>
            <div className="space-y-2 max-h-48 overflow-y-auto border border-gray-200 rounded-lg p-2">
              {agents.map(a => (
                <label key={a.id} className="flex items-center gap-2 cursor-pointer hover:bg-gray-50 p-1 rounded">
                  <input
                    type="checkbox"
                    checked={selectedAgentIds.includes(a.id)}
                    onChange={() => toggleAgent(a.id)}
                    className="rounded border-gray-300"
                  />
                  <span className="text-sm text-gray-700">{a.name}</span>
                </label>
              ))}
            </div>
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <button type="button" onClick={onClose} className="px-4 py-2 text-sm rounded-lg border border-gray-300 hover:bg-gray-50">Cancel</button>
            <button type="submit" className="px-4 py-2 text-sm rounded-lg bg-gray-900 text-white hover:bg-gray-800">Save</button>
          </div>
        </form>
      </div>
    </div>
  )
}
