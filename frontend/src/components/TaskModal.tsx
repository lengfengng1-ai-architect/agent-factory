import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import type { Task, TaskStatus } from '../types'
import { agentApi, groupApi, taskApi } from '../api/client'
import WorkflowStepList from './WorkflowStepList'

type Tab = 'overview' | 'workflow'

interface Props {
  task?: Task | null
  onClose: () => void
  onSave: (data: {
    title: string;
    description: string;
    status: TaskStatus;
    assignee_type: 'agent' | 'group';
    assignee_id: number | null;
    auto_execute: boolean;
    file_root_dir: string;
  }) => void
}

export default function TaskModal({ task, onClose, onSave }: Props) {
  const [activeTab, setActiveTab] = useState<Tab>('overview')

  // Auto-switch to workflow tab when waiting for feedback
  useEffect(() => {
    if (task?.workflow_status === 'waiting_feedback') {
      setActiveTab('workflow')
    }
  }, [task?.workflow_status])
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [status, setStatus] = useState<TaskStatus>('pending')
  const [assigneeType, setAssigneeType] = useState<'agent' | 'group'>('agent')
  const [assigneeId, setAssigneeId] = useState<number | null>(null)
  const [autoExecute, setAutoExecute] = useState(false)
  const [fileRootDir, setFileRootDir] = useState('')

  const qc = useQueryClient()
  const { data: agents = [] } = useQuery({ queryKey: ['agents'], queryFn: agentApi.list })
  const { data: groups = [] } = useQuery({ queryKey: ['groups'], queryFn: groupApi.list })

  const { data: workflowData } = useQuery({
    queryKey: ['task_workflow', task?.id],
    queryFn: () => taskApi.getWorkflowProgress(task!.id),
    enabled: !!task && activeTab === 'workflow',
    refetchInterval: 5000,
  })

  const breakdown = useMutation({
    mutationFn: () => taskApi.breakdown(task!.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['task_workflow', task?.id] }),
  })

  useEffect(() => {
    if (task) {
      setTitle(task.title)
      setDescription(task.description)
      setStatus(task.status)
      setAssigneeType(task.assignee_type)
      setAssigneeId(task.assignee_id)
      setAutoExecute(task.auto_execute ?? false)
      setFileRootDir(task.file_root_dir || '')
    } else {
      setTitle('')
      setDescription('')
      setStatus('pending')
      setAssigneeType('agent')
      setAssigneeId(null)
      setAutoExecute(false)
      setFileRootDir('')
    }
    setActiveTab('overview')
  }, [task])

  const candidates = assigneeType === 'agent' ? agents : groups
  const hasAssignee = assigneeId !== null && assigneeId !== 0

  const handleSave = () => {
    onSave({
      title,
      description,
      status,
      assignee_type: assigneeType,
      assignee_id: hasAssignee ? assigneeId : null,
      auto_execute: hasAssignee ? autoExecute : false,
      file_root_dir: fileRootDir,
    })
    onClose()
  }

  const hasWorkflow = !!task?.workflow_plan || (workflowData?.steps && workflowData.steps.length > 0)

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50" onClick={onClose}>
      <div className="bg-white rounded-xl p-6 w-full max-w-lg shadow-xl max-h-[90vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
        <h2 className="text-lg font-bold mb-4">{task ? 'Edit Task' : 'New Task'}</h2>

        {/* Tabs */}
        <div className="flex border-b border-gray-200 mb-4">
          <button
            onClick={() => setActiveTab('overview')}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
              activeTab === 'overview'
                ? 'border-gray-900 text-gray-900'
                : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}
          >
            概览
          </button>
          <button
            onClick={() => setActiveTab('workflow')}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
              activeTab === 'workflow'
                ? 'border-gray-900 text-gray-900'
                : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}
          >
            工作流
          </button>
        </div>

        {activeTab === 'overview' && (
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
                <select
                  className="mt-1 w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
                  value={assigneeType}
                  onChange={e => {
                    setAssigneeType(e.target.value as 'agent' | 'group')
                    setAssigneeId(null)
                    setAutoExecute(false)
                  }}
                >
                  <option value="agent">Agent</option>
                  <option value="group">Group</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700">Assignee</label>
                <select
                  className="mt-1 w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
                  value={assigneeId ?? ''}
                  onChange={e => {
                    const val = e.target.value ? Number(e.target.value) : null
                    setAssigneeId(val)
                    if (!val) setAutoExecute(false)
                  }}
                >
                  <option value="">无（手动任务）</option>
                  {candidates.map(c => (
                    <option key={c.id} value={c.id}>{c.name}</option>
                  ))}
                </select>
              </div>
            </div>

            {hasAssignee && (
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={autoExecute}
                  onChange={e => setAutoExecute(e.target.checked)}
                  className="rounded border-gray-300"
                />
                <span className="text-sm text-gray-700">拖入 In Progress 后自动执行</span>
              </label>
            )}

            <div>
              <label className="block text-sm font-medium text-gray-700">文件访问根目录</label>
              <input
                className="mt-1 w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
                placeholder="留空使用 Agent 默认 workspace"
                value={fileRootDir}
                onChange={e => setFileRootDir(e.target.value)}
              />
              <p className="text-xs text-gray-400 mt-1">Agent 文件操作将被限制在此目录内</p>
            </div>

            {/* Result display */}
            {task && task.status === 'in_progress' && (
              <div className="bg-blue-50 border border-blue-200 rounded-lg p-3">
                <div className="text-xs font-medium text-blue-800 mb-1">执行状态</div>
                <div className="text-sm text-blue-700">Agent 正在处理中，请稍后刷新查看结果...</div>
                {task.progress !== undefined && task.progress > 0 && (
                  <div className="mt-2 h-1.5 bg-blue-200 rounded-full overflow-hidden">
                    <div className="h-full bg-blue-500 rounded-full transition-all" style={{ width: `${task.progress}%` }} />
                  </div>
                )}
              </div>
            )}

            {task && task.status === 'completed' && task.result && (
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">执行结果</label>
                <div className="bg-gray-50 border border-gray-200 rounded-lg p-3 max-h-64 overflow-y-auto">
                  <div className="text-sm text-gray-800 whitespace-pre-wrap leading-relaxed">{task.result}</div>
                </div>
              </div>
            )}

            <div className="flex justify-end gap-2 pt-2">
              <button onClick={onClose} className="px-4 py-2 text-sm rounded-lg border border-gray-300 hover:bg-gray-50">Cancel</button>
              <button onClick={handleSave} className="px-4 py-2 text-sm rounded-lg bg-gray-900 text-white hover:bg-gray-800">Save</button>
            </div>
          </div>
        )}

        {activeTab === 'workflow' && (
          <div className="space-y-4">
            {!task && (
              <div className="text-center text-gray-400 text-sm py-8">保存任务后可查看工作流</div>
            )}
            {task && !hasWorkflow && (
              <div className="text-center py-8">
                <p className="text-sm text-gray-500 mb-4">当前任务尚未拆解为工作流</p>
                <button
                  onClick={() => breakdown.mutate()}
                  disabled={breakdown.isPending}
                  className="px-4 py-2 text-sm rounded-lg bg-gray-900 text-white hover:bg-gray-800 disabled:opacity-50"
                >
                  {breakdown.isPending ? '拆解中...' : '自动拆解为工作流'}
                </button>
              </div>
            )}
            {task && hasWorkflow && workflowData && (
              <>
                <div className="flex items-center justify-between">
                  <div className="text-sm text-gray-700">
                    进度: <span className="font-medium">{workflowData.completed_steps}/{workflowData.total_steps}</span>
                  </div>
                  <div className="text-xs text-gray-500">
                    {workflowData.workflow_status === 'running' && '执行中'}
                    {workflowData.workflow_status === 'completed' && '已完成'}
                    {workflowData.workflow_status === 'failed' && '失败'}
                    {workflowData.workflow_status === 'waiting_feedback' && '待确认'}
                  </div>
                </div>
                <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-indigo-500 rounded-full transition-all"
                    style={{ width: `${workflowData.progress}%` }}
                  />
                </div>
                <WorkflowStepList taskId={task.id} steps={workflowData.steps} />
              </>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
