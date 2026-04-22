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

  const isRunning = task.status === 'in_progress' && (task.progress ?? 0) < 100
  const progress = task.progress ?? 0

  return (
    <div ref={setNodeRef} style={style} className={`bg-white rounded-lg border ${statusColor} shadow-sm cursor-pointer hover:shadow-md transition-shadow overflow-hidden`} onClick={() => onEdit(task)}>
      {/* Progress bar */}
      {task.status === 'in_progress' && (
        <div className="h-1 w-full bg-gray-100">
          <div
            className={`h-full rounded-r-full transition-all duration-500 ${isRunning ? 'bg-gradient-to-r from-blue-400 to-indigo-500 animate-pulse' : 'bg-blue-500'}`}
            style={{ width: `${Math.max(5, progress)}%` }}
          />
        </div>
      )}
      {task.status === 'completed' && (
        <div className="h-1 w-full bg-green-100">
          <div className="h-full bg-green-500 rounded-r-full" style={{ width: '100%' }} />
        </div>
      )}

      <div className="p-3">
        <div className="flex items-start gap-2">
          <div {...listeners} {...attributes} className="mt-0.5 text-gray-400 hover:text-gray-600 cursor-grab active:cursor-grabbing">
            <GripVertical size={16} />
          </div>
          <div className="flex-1 min-w-0">
            <h4 className="text-sm font-medium text-gray-900 truncate">{task.title}</h4>
            <p className="text-xs text-gray-500 mt-0.5 line-clamp-2">{task.description}</p>
            <div className="mt-2 flex items-center gap-2 flex-wrap">
              {task.assignee_id ? (
                <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${
                  task.assignee_type === 'agent' ? 'bg-purple-50 text-purple-700' : 'bg-blue-50 text-blue-700'
                }`}>
                  {task.assignee_type === 'agent' ? 'AGENT' : 'GROUP'}
                </span>
              ) : (
                <span className="text-[10px] px-1.5 py-0.5 rounded-full font-medium bg-gray-100 text-gray-600">
                  MANUAL
                </span>
              )}
              {task.auto_execute && task.assignee_id && (
                <span className="text-[10px] px-1.5 py-0.5 rounded-full font-medium bg-orange-50 text-orange-700">
                  AUTO
                </span>
              )}
              {task.status === 'in_progress' && (
                <span className="text-[10px] text-blue-600 font-medium">{progress}%</span>
              )}
              {task.status === 'completed' && task.result && (
                <span className="text-[10px] px-1.5 py-0.5 rounded-full font-medium bg-green-50 text-green-700">
                  有结果
                </span>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
