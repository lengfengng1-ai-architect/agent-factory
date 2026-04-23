import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import type { Task, TaskStatus } from '../types'
import { agentApi, groupApi, taskApi, fileApi } from '../api/client'
import ArtifactViewer from './ArtifactViewer'
import { Pencil, FolderOpen } from 'lucide-react'

type ModalMode = 'view' | 'edit' | 'create'

interface Props {
  task?: Task | null
  mode: ModalMode
  onClose: () => void
  onSave: (data: {
    title: string;
    description: string;
    status: TaskStatus;
    assignee_type: 'agent' | 'group';
    assignee_id: number | null;
    auto_execute: boolean;
    file_root_dir: string;
    workflow_config?: Record<string, any>;
  }) => void
  onSwitchEdit?: () => void
}

export default function TaskModal({ task, mode, onClose, onSave, onSwitchEdit }: Props) {
  const isView = mode === 'view'
  const isCreate = mode === 'create'

  const [activeTab, setActiveTab] = useState<'overview'>('overview')

  // Form states
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [status, setStatus] = useState<TaskStatus>('pending')
  const [assigneeType, setAssigneeType] = useState<'agent' | 'group'>('agent')
  const [assigneeId, setAssigneeId] = useState<number | null>(null)
  const [fileRootDir, setFileRootDir] = useState('')
  const [manualConfirm, setManualConfirm] = useState(false)
  // Artifacts viewer
  const [showArtifacts, setShowArtifacts] = useState(false)

  const qc = useQueryClient()
  const { data: agents = [] } = useQuery({ queryKey: ['agents'], queryFn: agentApi.list })
  const { data: groups = [] } = useQuery({ queryKey: ['groups'], queryFn: groupApi.list })

  const { data: workflowData } = useQuery({
    queryKey: ['task_workflow', task?.id],
    queryFn: () => taskApi.getWorkflowProgress(task!.id),
    enabled: false,
    refetchInterval: 5000,
  })

  const updateTaskConfig = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<Task> }) => taskApi.update(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['tasks'] }),
  })

  const { data: artifactsData } = useQuery({
    queryKey: ['task_artifacts', task?.id],
    queryFn: () => fileApi.listTaskArtifacts(task!.id),
    enabled: !!task && showArtifacts,
  })

  useEffect(() => {
    if (task) {
      setTitle(task.title)
      setDescription(task.description)
      setStatus(task.status)
      setAssigneeType(task.assignee_type)
      setAssigneeId(task.assignee_id)
      setFileRootDir(task.file_root_dir || '')
      setManualConfirm(task.workflow_config?.disable_checkpoints === false)
    } else {
      setTitle('')
      setDescription('')
      setStatus('pending')
      setAssigneeType('agent')
      setAssigneeId(null)
      setFileRootDir('')
      setManualConfirm(false)
    }
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
      auto_execute: hasAssignee,
      file_root_dir: fileRootDir,
      workflow_config: { disable_checkpoints: !manualConfirm },
    })
    onClose()
  }

  const hasWorkflow = !!task?.workflow_plan || (workflowData?.steps && workflowData.steps.length > 0)

  // Global checkpoint toggle handler
  const handleToggleCheckpoints = (checked: boolean) => {
    setManualConfirm(checked)
    if (task) {
      const cfg = (task as any).workflow_config || {}
      updateTaskConfig.mutate({
        id: task.id,
        data: {
          workflow_config: { ...cfg, disable_checkpoints: !checked },
        } as any,
      })
    }
  }

  const checkpointsEnabled = manualConfirm

  const tabConfig = [{ id: 'overview' as const, label: '概览' }]

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50" onClick={onClose}>
      <div className="bg-white rounded-xl p-6 w-full max-w-lg shadow-xl max-h-[90vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
        {/* Header */}
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-bold">
            {isCreate ? '新建任务' : isView ? '查看任务' : '编辑任务'}
          </h2>
          {isView && onSwitchEdit && (
            <button
              onClick={onSwitchEdit}
              className="flex items-center gap-1 text-xs px-2 py-1 bg-gray-100 text-gray-700 rounded hover:bg-gray-200"
            >
              <Pencil size={12} /> 编辑
            </button>
          )}
        </div>

        {/* Tabs */}
        <div className="flex border-b border-gray-200 mb-4">
          {tabConfig.map(t => (
            <button
              key={t.id}
              onClick={() => setActiveTab(t.id)}
              className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
                activeTab === t.id
                  ? 'border-gray-900 text-gray-900'
                  : 'border-transparent text-gray-500 hover:text-gray-700'
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>

        {activeTab === 'overview' && (
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700">标题</label>
              <input
                className="mt-1 w-full border border-gray-300 rounded-lg px-3 py-2 text-sm disabled:bg-gray-50 disabled:text-gray-500"
                value={title}
                onChange={e => setTitle(e.target.value)}
                disabled={isView}
                required
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700">描述</label>
              <textarea
                className="mt-1 w-full border border-gray-300 rounded-lg px-3 py-2 text-sm disabled:bg-gray-50 disabled:text-gray-500"
                rows={3}
                value={description}
                onChange={e => setDescription(e.target.value)}
                disabled={isView}
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-sm font-medium text-gray-700">执行者类型</label>
                <select
                  className="mt-1 w-full border border-gray-300 rounded-lg px-3 py-2 text-sm disabled:bg-gray-50 disabled:text-gray-500"
                  value={assigneeType}
                  onChange={e => {
                    setAssigneeType(e.target.value as 'agent' | 'group')
                    setAssigneeId(null)
                  }}
                  disabled={isView}
                >
                  <option value="agent">Agent</option>
                  <option value="group">Group</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700">执行者</label>
                <select
                  className="mt-1 w-full border border-gray-300 rounded-lg px-3 py-2 text-sm disabled:bg-gray-50 disabled:text-gray-500"
                  value={assigneeId ?? ''}
                  onChange={e => {
                    const val = e.target.value ? Number(e.target.value) : null
                    setAssigneeId(val)
                  }}
                  disabled={isView}
                >
                  <option value="">无（手动任务）</option>
                  {candidates.map(c => (
                    <option key={c.id} value={c.id}>{c.name}</option>
                  ))}
                </select>
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700">文件访问根目录</label>
              <input
                className="mt-1 w-full border border-gray-300 rounded-lg px-3 py-2 text-sm disabled:bg-gray-50 disabled:text-gray-500"
                placeholder="留空使用 Agent 默认 workspace"
                value={fileRootDir}
                onChange={e => setFileRootDir(e.target.value)}
                disabled={isView}
              />
              <p className="text-xs text-gray-400 mt-1">Agent 文件操作将被限制在此目录内</p>
            </div>

            {/* Checkpoint toggle */}
            <div className="flex items-center justify-between bg-gray-50 rounded-lg px-3 py-2">
              <label className={`flex items-center gap-2 text-sm ${isView ? 'cursor-default' : 'cursor-pointer'}`}>
                <input
                  type="checkbox"
                  checked={checkpointsEnabled}
                  onChange={e => handleToggleCheckpoints(e.target.checked)}
                  disabled={isView}
                  className="rounded border-gray-300"
                />
                <span className="text-gray-700">启用人工确认</span>
              </label>
              <span className="text-[10px] text-gray-400">
                {checkpointsEnabled ? '执行到 checkpoint 会暂停等待确认' : '所有步骤自动连续执行'}
              </span>
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

            {/* Final result / artifact */}
            {task && task.status === 'completed' && task.result && (
              <div>
                <div className="flex items-center justify-between mb-1">
                  <label className="block text-sm font-medium text-gray-700">执行结果</label>
                  {hasWorkflow && (
                    <button
                      onClick={() => setShowArtifacts(true)}
                      className="flex items-center gap-1 text-xs px-2 py-1 bg-gray-100 text-gray-600 rounded hover:bg-gray-200"
                    >
                      <FolderOpen size={12} /> 查看全部产物
                    </button>
                  )}
                </div>
                <div className="bg-gray-50 border border-gray-200 rounded-lg p-3 max-h-64 overflow-y-auto">
                  <div className="text-sm text-gray-800 whitespace-pre-wrap leading-relaxed">{task.result}</div>
                </div>
              </div>
            )}

            {/* Buttons */}
            {isView ? (
              <div className="flex justify-end gap-2 pt-2">
                <button onClick={onClose} className="px-4 py-2 text-sm rounded-lg border border-gray-300 hover:bg-gray-50">关闭</button>
              </div>
            ) : (
              <div className="flex justify-end gap-2 pt-2">
                <button onClick={onClose} className="px-4 py-2 text-sm rounded-lg border border-gray-300 hover:bg-gray-50">取消</button>
                <button onClick={handleSave} className="px-4 py-2 text-sm rounded-lg bg-gray-900 text-white hover:bg-gray-800">
                  {isCreate ? '创建' : '保存'}
                </button>
              </div>
            )}
          </div>
        )}


      </div>
      {showArtifacts && artifactsData && (
        <ArtifactViewer artifacts={artifactsData.artifacts} onClose={() => setShowArtifacts(false)} />
      )}
    </div>
  )
}
