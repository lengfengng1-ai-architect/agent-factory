import { useState, useEffect } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import type { Agent } from '../types'
import { agentApi } from '../api/client'
import { FeishuStatus } from './FeishuStatus'

interface Props {
  agent: Agent
  onClose: () => void
}

export default function FeishuConfigModal({ agent, onClose }: Props) {
  const qc = useQueryClient()
  const [enableFeishu, setEnableFeishu] = useState(false)
  const [appId, setAppId] = useState('')
  const [appSecret, setAppSecret] = useState('')

  useEffect(() => {
    const cfg = (agent.config as Record<string, any>)?.feishu || {}
    setEnableFeishu(!!cfg.enabled)
    setAppId(cfg.app_id || '')
    setAppSecret(cfg.app_secret || '')
  }, [agent])

  const mutation = useMutation({
    mutationFn: (data: Partial<Agent>) => agentApi.update(agent.id, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['agents'] })
      onClose()
    },
  })

  const handleSave = () => {
    const newConfig = {
      ...(agent.config || {}),
      feishu: enableFeishu
        ? { enabled: true, app_id: appId, app_secret: appSecret }
        : { enabled: false },
    }
    mutation.mutate({ config: newConfig })
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50" onClick={onClose}>
      <div className="bg-white rounded-xl p-6 w-full max-w-md shadow-xl" onClick={e => e.stopPropagation()}>
        <h2 className="text-lg font-bold mb-4">🤖 配置飞书机器人 — {agent.name}</h2>
        <div className="space-y-4">
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={enableFeishu}
              onChange={e => setEnableFeishu(e.target.checked)}
              className="rounded border-gray-300"
            />
            <span className="text-sm text-gray-700">启用飞书机器人</span>
          </label>

          {enableFeishu && (
            <>
              <p className="text-xs text-blue-600 bg-blue-50 px-2 py-1 rounded">
                当前使用 WebSocket 长连接模式，无需公网域名和 Webhook 配置。保存后自动连接飞书服务器。
              </p>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">App ID</label>
                <input
                  className="w-full border border-gray-300 rounded-lg px-3 py-1.5 text-sm"
                  value={appId}
                  onChange={e => setAppId(e.target.value)}
                  placeholder="cli_xxxxxxxxxxxx"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">App Secret</label>
                <input
                  type="password"
                  className="w-full border border-gray-300 rounded-lg px-3 py-1.5 text-sm"
                  value={appSecret}
                  onChange={e => setAppSecret(e.target.value)}
                  placeholder="xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
                />
              </div>
            </>
          )}

          <FeishuStatus agentId={agent.id} />

          <div className="flex justify-end gap-2 pt-2">
            <button
              onClick={onClose}
              className="px-4 py-2 text-sm rounded-lg border border-gray-300 hover:bg-gray-50"
            >
              Cancel
            </button>
            <button
              onClick={handleSave}
              disabled={mutation.isPending}
              className="px-4 py-2 text-sm rounded-lg bg-gray-900 text-white hover:bg-gray-800 disabled:opacity-50"
            >
              {mutation.isPending ? '保存中...' : 'Save'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
