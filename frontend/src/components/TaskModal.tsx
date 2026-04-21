import { useState, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import type { Task, TaskStatus } from '../types'
import { agentApi, groupApi } from '../api/client'

interface Props {
  task?: Task | null
  onClose: () => void
  onSave: (data: { title: string; description: string; status: TaskStatus; assignee_type: 'agent' | 'group'; assignee_id: number }) => void
}

export default function TaskModal({ task, onClose, onSave }: Props) {
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [status, setStatus] = useState<TaskStatus>('pending')
  const [assigneeType, setAssigneeType] = useState<'agent' | 'group'>('agent')
  const [assigneeId, setAssigneeId] = useState<number>(0)

  const { data: agents = [] } = useQuery({ queryKey: ['agents'], queryFn: agentApi.list })
  const { data: groups = [] } = useQuery({ queryKey: ['groups'], queryFn: groupApi.list })

  useEffect(() => {
    if (task) {
      setTitle(task.title)
      setDescription(task.description)
      setStatus(task.status)
      setAssigneeType(task.assignee_type)
      setAssigneeId(task.assignee_id)
    } else {
      setTitle('')
      setDescription('')
      setStatus('pending')
      setAssigneeType('agent')
      setAssigneeId(agents[0]?.id || 0)
    }
  }, [task, agents])

  const candidates = assigneeType === 'agent' ? agents : groups

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50" onClick={onClose}>
      <div className="bg-white rounded-xl p-6 w-full max-w-md shadow-xl" onClick={e => e.stopPropagation()}>
        <h2 className="text-lg font-bold mb-4">{task ? 'Edit Task' : 'New Task'}</h2>
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700">Title</label>
            <input className="mt-1 w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" value={title} onChange={e => setTitle(e.target.value)} required />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700">Description</label>
            <textarea className="mt-1 w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" rows={3} value={description} onChange={e => setDescription(e.target.value)} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium text-gray-700">Assignee Type</label>
              <select className="mt-1 w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" value={assigneeType} onChange={e => { setAssigneeType(e.target.value as 'agent' | 'group'); setAssigneeId(0) }}>
                <option value="agent">Agent</option>
                <option value="group">Group</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700">Assignee</label>
              <select className="mt-1 w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" value={assigneeId} onChange={e => setAssigneeId(Number(e.target.value))}>
                {candidates.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            </div>
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <button onClick={onClose} className="px-4 py-2 text-sm rounded-lg border border-gray-300 hover:bg-gray-50">Cancel</button>
            <button onClick={() => { onSave({ title, description, status, assignee_type: assigneeType, assignee_id: assigneeId }); onClose() }} className="px-4 py-2 text-sm rounded-lg bg-gray-900 text-white hover:bg-gray-800">Save</button>
          </div>
        </div>
      </div>
    </div>
  )
}
