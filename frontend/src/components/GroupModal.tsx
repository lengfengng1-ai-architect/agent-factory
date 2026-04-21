import { useState, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import type { Group } from '../types'
import { agentApi } from '../api/client'

interface Props {
  group?: Group | null
  onClose: () => void
  onSave: (data: { name: string; description: string; agent_ids: number[] }) => void
}

export default function GroupModal({ group, onClose, onSave }: Props) {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [selected, setSelected] = useState<number[]>([])
  const { data: agents = [] } = useQuery({ queryKey: ['agents'], queryFn: agentApi.list })

  useEffect(() => {
    if (group) {
      setName(group.name)
      setDescription(group.description)
      setSelected(group.agent_ids || [])
    } else {
      setName('')
      setDescription('')
      setSelected([])
    }
  }, [group])

  const toggle = (id: number) => {
    setSelected(prev => prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id])
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50" onClick={onClose}>
      <div className="bg-white rounded-xl p-6 w-full max-w-lg shadow-xl" onClick={e => e.stopPropagation()}>
        <h2 className="text-lg font-bold mb-4">{group ? 'Edit Group' : 'New Group'}</h2>
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700">Name</label>
            <input className="mt-1 w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" value={name} onChange={e => setName(e.target.value)} required />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700">Description</label>
            <textarea className="mt-1 w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" rows={2} value={description} onChange={e => setDescription(e.target.value)} />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">Select Agents</label>
            <div className="border border-gray-200 rounded-lg max-h-48 overflow-y-auto p-2 space-y-1">
              {agents.map(a => (
                <label key={a.id} className="flex items-center gap-2 px-2 py-1.5 hover:bg-gray-50 rounded cursor-pointer">
                  <input type="checkbox" checked={selected.includes(a.id)} onChange={() => toggle(a.id)} />
                  <span className="text-sm">{a.name}</span>
                </label>
              ))}
            </div>
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <button onClick={onClose} className="px-4 py-2 text-sm rounded-lg border border-gray-300 hover:bg-gray-50">Cancel</button>
            <button onClick={() => { onSave({ name, description, agent_ids: selected }); onClose() }} className="px-4 py-2 text-sm rounded-lg bg-gray-900 text-white hover:bg-gray-800">Save</button>
          </div>
        </div>
      </div>
    </div>
  )
}
