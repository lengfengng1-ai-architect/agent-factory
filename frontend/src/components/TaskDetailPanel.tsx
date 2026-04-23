import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { X, FolderOpen } from 'lucide-react'
import { taskApi, fileApi } from '../api/client'
import type { Task } from '../types'
import WorkflowStepList from './WorkflowStepList'
import ArtifactViewer from './ArtifactViewer'

interface Props {
  task: Task;
  onClose: () => void;
}

export default function TaskDetailPanel({ task, onClose }: Props) {
  const [showArtifacts, setShowArtifacts] = useState(false)
  const [activeTab, setActiveTab] = useState<'workflow' | 'result'>('workflow')

  const hasWorkflow = !!(task.workflow_plan || task.workflow_status)

  const { data: workflowData } = useQuery({
    queryKey: ['task_workflow', task.id],
    queryFn: () => taskApi.getWorkflowProgress(task.id),
    refetchInterval: 5000,
    enabled: hasWorkflow,
  })

  const { data: artifactsData } = useQuery({
    queryKey: ['task_artifacts', task.id],
    queryFn: () => fileApi.listTaskArtifacts(task.id),
    enabled: hasWorkflow,
  })

  const statusLabel: Record<string, string> = {
    pending: '待处理',
    in_progress: '进行中',
    completed: '已完成',
  }

  return (
    <div className="h-full flex flex-col overflow-hidden bg-white">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 shrink-0">
        <h3 className="font-semibold text-sm text-gray-900 truncate pr-2">{task.title}</h3>
        <button onClick={onClose} className="p-1 hover:bg-gray-100 rounded shrink-0">
          <X size={16} className="text-gray-500" />
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-hidden flex flex-col">
        {/* Tabs */}
        <div className="flex border-b border-gray-200 shrink-0">
          {hasWorkflow && (
            <button
              onClick={() => setActiveTab('workflow')}
              className={`flex-1 py-2.5 text-xs font-medium transition-colors ${
                activeTab === 'workflow'
                  ? 'text-gray-900 border-b-2 border-gray-900'
                  : 'text-gray-500 hover:text-gray-700'
              }`}
            >
              工作流
            </button>
          )}
          <button
            onClick={() => setActiveTab('result')}
            className={`flex-1 py-2.5 text-xs font-medium transition-colors ${
              activeTab === 'result'
                ? 'text-gray-900 border-b-2 border-gray-900'
                : 'text-gray-500 hover:text-gray-700'
            }`}
          >
            执行结果
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-4">
          {activeTab === 'workflow' && hasWorkflow && (
            <div className="space-y-4">
              {workflowData?.steps ? (
                <WorkflowStepList taskId={task.id} steps={workflowData.steps} />
              ) : (
                <div className="text-sm text-gray-400 py-4">加载中...</div>
              )}
            </div>
          )}
          {activeTab === 'result' && (
            <div className="space-y-4">
              {/* Info fields (always show for non-workflow tasks) */}
              {!hasWorkflow && (
                <>
                  <div>
                    <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">描述</h4>
                    <p className="text-sm text-gray-700">{task.description || '无描述'}</p>
                  </div>
                  <div>
                    <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">状态</h4>
                    <span className="text-sm text-gray-700">{statusLabel[task.status] || task.status}</span>
                  </div>
                  <div>
                    <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">执行者</h4>
                    <span className="text-sm text-gray-700">
                      {task.assignee_type === 'agent' ? 'Agent' : task.assignee_type === 'group' ? 'Group' : '未分配'}
                      {task.assignee_id ? ` (ID: ${task.assignee_id})` : ''}
                    </span>
                  </div>
                  {task.file_root_dir && (
                    <div>
                      <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">文件根目录</h4>
                      <span className="text-sm text-gray-700 font-mono">{task.file_root_dir}</span>
                    </div>
                  )}
                </>
              )}

              {/* Result */}
              {task.result && (
                <div>
                  {!hasWorkflow && <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">执行结果</h4>}
                  <div className="text-sm text-gray-700 bg-gray-50 p-3 rounded-lg whitespace-pre-wrap">{task.result}</div>
                </div>
              )}

              {/* Artifacts */}
              {artifactsData?.artifacts && artifactsData.artifacts.length > 0 && (
                <button
                  onClick={() => setShowArtifacts(true)}
                  className="flex items-center gap-1.5 text-sm px-3 py-1.5 bg-gray-900 text-white rounded-lg hover:bg-gray-800"
                >
                  <FolderOpen size={14} /> 查看产物 ({artifactsData.artifacts.length})
                </button>
              )}

              {!task.result && (!artifactsData?.artifacts || artifactsData.artifacts.length === 0) && (
                <div className="text-sm text-gray-400 py-4">暂无执行结果</div>
              )}
            </div>
          )}
        </div>
      </div>

      {showArtifacts && artifactsData?.artifacts && (
        <ArtifactViewer artifacts={artifactsData.artifacts} onClose={() => setShowArtifacts(false)} />
      )}
    </div>
  )
}
