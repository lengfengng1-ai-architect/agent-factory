import { useMutation, useQueryClient } from '@tanstack/react-query'
import type { WorkflowStep } from '../types'
import { taskApi } from '../api/client'

interface Props {
  taskId: number;
  steps: WorkflowStep[];
}

export default function WorkflowStepList({ taskId, steps }: Props) {
  const qc = useQueryClient()

  const confirm = useMutation({
    mutationFn: (stepId: number) => taskApi.confirmStep(taskId, stepId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['task_workflow', taskId] }),
  })
  const retry = useMutation({
    mutationFn: (stepId: number) => taskApi.retryStep(taskId, stepId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['task_workflow', taskId] }),
  })
  const skip = useMutation({
    mutationFn: (stepId: number) => taskApi.skipStep(taskId, stepId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['task_workflow', taskId] }),
  })

  const statusColor: Record<string, string> = {
    pending: 'bg-gray-100 text-gray-600',
    running: 'bg-blue-100 text-blue-700',
    completed: 'bg-green-100 text-green-700',
    failed: 'bg-red-100 text-red-700',
    waiting_feedback: 'bg-orange-100 text-orange-700',
    skipped: 'bg-gray-50 text-gray-400',
  }

  return (
    <div className="space-y-3">
      {steps.map(step => (
        <div key={step.id} className="border border-gray-200 rounded-lg p-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${statusColor[step.status] || 'bg-gray-100'}`}>
                {step.status === 'waiting_feedback' ? '待确认' : step.status}
              </span>
              {step.checkpoint && (
                <span className="text-[10px] bg-purple-100 text-purple-700 px-1.5 py-0.5 rounded">checkpoint</span>
              )}
              <span className="text-sm font-medium text-gray-900">{step.name}</span>
            </div>
            <div className="flex gap-1">
              {step.status === 'waiting_feedback' && (
                <>
                  <button onClick={() => confirm.mutate(step.id)} disabled={confirm.isPending} className="text-xs px-2 py-1 bg-green-600 text-white rounded hover:bg-green-700 disabled:opacity-50">确认</button>
                  <button onClick={() => retry.mutate(step.id)} disabled={retry.isPending} className="text-xs px-2 py-1 bg-orange-600 text-white rounded hover:bg-orange-700 disabled:opacity-50">重试</button>
                  <button onClick={() => skip.mutate(step.id)} disabled={skip.isPending} className="text-xs px-2 py-1 bg-gray-500 text-white rounded hover:bg-gray-600 disabled:opacity-50">跳过</button>
                </>
              )}
              {step.status === 'failed' && (
                <button onClick={() => retry.mutate(step.id)} disabled={retry.isPending} className="text-xs px-2 py-1 bg-orange-600 text-white rounded hover:bg-orange-700 disabled:opacity-50">重试</button>
              )}
            </div>
          </div>
          {step.description && (
            <p className="text-xs text-gray-500 mt-1 line-clamp-2">{step.description}</p>
          )}
          {step.result && (
            <p className="text-xs text-gray-600 mt-1 bg-gray-50 p-2 rounded line-clamp-3">{step.result}</p>
          )}
          {step.artifact_path && (
            <p className="text-[10px] text-gray-400 mt-1">产物: {step.artifact_path}</p>
          )}
          {step.retry_count > 0 && (
            <p className="text-[10px] text-orange-500 mt-0.5">已重试 {step.retry_count} 次</p>
          )}
        </div>
      ))}
      {steps.length === 0 && (
        <div className="text-center text-gray-400 text-sm py-8">暂无工作流步骤</div>
      )}
    </div>
  )
}
