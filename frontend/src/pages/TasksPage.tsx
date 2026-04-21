import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { DndContext, PointerSensor, useSensor, useSensors, useDroppable } from '@dnd-kit/core'
import type { DragEndEvent } from '@dnd-kit/core'
import { Plus } from 'lucide-react'
import { taskApi } from '../api/client'
import type { Task, TaskStatus } from '../types'
import TaskCard from '../components/TaskCard'
import TaskModal from '../components/TaskModal'

const COLUMNS: { id: TaskStatus; title: string; bg: string }[] = [
  { id: 'pending', title: 'To Do', bg: 'bg-gray-50' },
  { id: 'in_progress', title: 'In Progress', bg: 'bg-blue-50/50' },
  { id: 'completed', title: 'Done', bg: 'bg-green-50/50' },
]

function Column({ id, title, bg, children, count }: { id: string; title: string; bg: string; children: React.ReactNode; count: number }) {
  const { setNodeRef, isOver } = useDroppable({ id })
  return (
    <div ref={setNodeRef} className={`${bg} rounded-xl border ${isOver ? 'border-blue-400 ring-2 ring-blue-100' : 'border-gray-200'} p-3 min-h-[300px]`}>
      <div className="flex items-center justify-between mb-3 px-1">
        <h3 className="text-sm font-semibold text-gray-700">{title}</h3>
        <span className="text-xs bg-white text-gray-500 px-2 py-0.5 rounded-full border border-gray-200">{count}</span>
      </div>
      <div className="space-y-2">{children}</div>
    </div>
  )
}

export default function TasksPage() {
  const [modalOpen, setModalOpen] = useState(false)
  const [editing, setEditing] = useState<Task | null>(null)
  const qc = useQueryClient()

  const { data: tasks = [] } = useQuery({ queryKey: ['tasks'], queryFn: () => taskApi.list() })

  const create = useMutation({ mutationFn: taskApi.create, onSuccess: () => qc.invalidateQueries({ queryKey: ['tasks'] }) })
  const update = useMutation({ mutationFn: ({ id, data }: { id: number; data: Partial<Task> }) => taskApi.update(id, data), onSuccess: () => qc.invalidateQueries({ queryKey: ['tasks'] }) })

  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 5 } }))

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event
    if (!over) return
    const taskId = Number(String(active.id).replace('task-', ''))
    const newStatus = String(over.id) as TaskStatus
    const task = tasks.find(t => t.id === taskId)
    if (task && task.status !== newStatus) {
      update.mutate({ id: taskId, data: { status: newStatus } })
    }
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-2xl font-bold">Tasks</h2>
        <button onClick={() => { setEditing(null); setModalOpen(true) }} className="flex items-center gap-2 px-4 py-2 bg-gray-900 text-white rounded-lg text-sm hover:bg-gray-800">
          <Plus size={16} /> New Task
        </button>
      </div>

      <DndContext sensors={sensors} onDragEnd={handleDragEnd}>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {COLUMNS.map(col => {
            const colTasks = tasks.filter(t => t.status === col.id)
            return (
              <Column key={col.id} id={col.id} title={col.title} bg={col.bg} count={colTasks.length}>
                {colTasks.map(task => (
                  <TaskCard key={task.id} task={task} onEdit={t => { setEditing(t); setModalOpen(true) }} />
                ))}
              </Column>
            )
          })}
        </div>
      </DndContext>

      {modalOpen && <TaskModal task={editing} onClose={() => setModalOpen(false)} onSave={data => {
        if (editing) update.mutate({ id: editing.id, data })
        else create.mutate(data)
      }} />}
    </div>
  )
}
