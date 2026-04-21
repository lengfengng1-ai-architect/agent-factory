import { useDraggable } from '@dnd-kit/core'
import type { Task } from '../types'
import { GripVertical } from 'lucide-react'

interface Props {
  task: Task
  onEdit: (task: Task) => void
}

export default function TaskCard({ task, onEdit }: Props) {
  const { attributes, listeners, setNodeRef, transform } = useDraggable({ id: `task-${task.id}`, data: task })
  const style = transform ? { transform: `translate3d(${transform.x}px, ${transform.y}px, 0)` } : undefined

  const statusColor = {
    pending: 'border-gray-200',
    in_progress: 'border-blue-300',
    completed: 'border-green-300',
  }[task.status]

  return (
    <div ref={setNodeRef} style={style} className={`bg-white rounded-lg border ${statusColor} p-3 shadow-sm cursor-pointer hover:shadow-md transition-shadow`} onClick={() => onEdit(task)}>
      <div className="flex items-start gap-2">
        <div {...listeners} {...attributes} className="mt-0.5 text-gray-400 hover:text-gray-600 cursor-grab active:cursor-grabbing">
          <GripVertical size={16} />
        </div>
        <div className="flex-1 min-w-0">
          <h4 className="text-sm font-medium text-gray-900 truncate">{task.title}</h4>
          <p className="text-xs text-gray-500 mt-0.5 line-clamp-2">{task.description}</p>
          <div className="mt-2 flex items-center gap-2">
            <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${
              task.assignee_type === 'agent' ? 'bg-purple-50 text-purple-700' : 'bg-blue-50 text-blue-700'
            }`}>
              {task.assignee_type === 'agent' ? 'AGENT' : 'GROUP'}
            </span>
            <span className="text-[10px] text-gray-400">ID:{task.assignee_id}</span>
          </div>
        </div>
      </div>
    </div>
  )
}
