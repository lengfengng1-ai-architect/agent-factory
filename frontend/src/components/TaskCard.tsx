import { useDraggable } from '@dnd-kit/core'
import type { Task } from '../types'
import { GripVertical, Pencil, Trash2 } from 'lucide-react'

interface Props {
  task: Task
  onSelect: (task: Task) => void
  onEdit: (task: Task) => void
  onDelete?: (task: Task) => void
  isSelected?: boolean
  isOverlay?: boolean
}

export default function TaskCard({ task, onSelect, onEdit, onDelete, isSelected, isOverlay }: Props) {
  const { attributes, listeners, setNodeRef, transform } = useDraggable({
    id: `task-${task.id}`,
    data: task,
    disabled: isOverlay,
  })

  const style = isOverlay
    ? undefined
    : transform
      ? { transform: `translate3d(${transform.x}px, ${transform.y}px, 0)`, zIndex: 9999 }
      : undefined

  const statusColor = {
    pending: 'border-gray-200',
    in_progress: 'border-blue-300',
    completed: 'border-green-300',
  }[task.status]

  const isRunning = task.status === 'in_progress' && (task.progress ?? 0) < 100
  const progress = task.progress ?? 0

  return (
    <div
      ref={isOverlay ? undefined : setNodeRef}
      style={style}
      className={`group bg-white rounded-lg border ${isSelected ? 'border-indigo-400 ring-2 ring-indigo-100' : statusColor} shadow-sm cursor-pointer hover:shadow-md transition-shadow overflow-hidden ${isOverlay ? 'rotate-2 shadow-xl cursor-grabbing' : ''}`}
      onClick={() => onSelect(task)}
    >
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
          <div {...(isOverlay ? {} : listeners)} {...(isOverlay ? {} : attributes)} className="mt-0.5 text-gray-400 hover:text-gray-600 cursor-grab active:cursor-grabbing">
            <GripVertical size={16} />
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-start justify-between gap-1">
              <h4 className="text-sm font-medium text-gray-900 truncate">{task.title}</h4>
              <div className="flex items-center gap-0.5 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">
                <button
                  onClick={(e) => {
                    e.stopPropagation()
                    onEdit(task)
                  }}
                  className="text-gray-400 hover:text-gray-600 p-0.5 rounded hover:bg-gray-100"
                  title="编辑"
                >
                  <Pencil size={12} />
                </button>
                {onDelete && (
                  <button
                    onClick={(e) => {
                      e.stopPropagation()
                      if (confirm(`确定要删除任务「${task.title}」吗？`)) {
                        onDelete(task)
                      }
                    }}
                    className="text-gray-400 hover:text-red-600 p-0.5 rounded hover:bg-red-50"
                    title="删除"
                  >
                    <Trash2 size={12} />
                  </button>
                )}
              </div>
            </div>
            <p className="text-xs text-gray-500 mt-0.5 line-clamp-2">{task.description}</p>

            {/* Workflow progress */}
            {task.workflow_plan && task.total_steps !== undefined && task.total_steps > 0 && (
              <div className="mt-2">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-[10px] text-gray-500">工作流</span>
                  <span className="text-[10px] text-gray-500">{task.completed_steps ?? 0}/{task.total_steps}</span>
                </div>
                <div className="h-1 w-full bg-gray-100 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-indigo-500 rounded-full transition-all"
                    style={{ width: `${Math.round(((task.completed_steps ?? 0) / task.total_steps) * 100)}%` }}
                  />
                </div>
                <div className="mt-1">
                  {task.workflow_status === 'waiting_feedback' && (
                    <span className="text-[10px] px-1.5 py-0.5 rounded-full font-medium bg-orange-100 text-orange-700">待确认</span>
                  )}
                  {task.workflow_status === 'running' && (
                    <span className="text-[10px] px-1.5 py-0.5 rounded-full font-medium bg-blue-100 text-blue-700">执行中</span>
                  )}
                  {task.workflow_status === 'completed' && (
                    <span className="text-[10px] px-1.5 py-0.5 rounded-full font-medium bg-green-100 text-green-700">已完成</span>
                  )}
                  {task.workflow_status === 'failed' && (
                    <span className="text-[10px] px-1.5 py-0.5 rounded-full font-medium bg-red-100 text-red-700">失败</span>
                  )}
                </div>
              </div>
            )}

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
