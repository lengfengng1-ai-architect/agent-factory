import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { ChevronDown, RefreshCw } from 'lucide-react'
import { providerApi } from '../api/client'
import type { Agent, Provider } from '../types'
import { FeishuStatus } from './FeishuStatus'

interface Props {
  agent?: Agent | null
  onClose: () => void
  onSave: (data: { name: string; description: string; config: Record<string, unknown>; system_prompt: string; model: string; api_url: string; api_key: string; provider: string }) => void
}

export default function AgentModal({ agent, onClose, onSave }: Props) {
  const queryClient = useQueryClient()

  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [config, setConfig] = useState('{}')
  const [systemPrompt, setSystemPrompt] = useState('')
  const [enableBrowsing, setEnableBrowsing] = useState(false)
  const [enableFileAccess, setEnableFileAccess] = useState(false)
  const [fileAccessRoot, setFileAccessRoot] = useState('./workspace')
  const [enableFeishu, setEnableFeishu] = useState(false)
  const [feishuAppId, setFeishuAppId] = useState('')
  const [feishuAppSecret, setFeishuAppSecret] = useState('')
  const [model, setModel] = useState('')
  const [apiUrl, setApiUrl] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [selectedProvider, setSelectedProvider] = useState<Provider | null>(null)


  const { data: providers } = useQuery({
    queryKey: ['providers'],
    queryFn: () => providerApi.list(),
  })

  const { data: models } = useQuery({
    queryKey: ['providerModels', selectedProvider?.id],
    queryFn: () => providerApi.getModels(selectedProvider!.id),
    enabled: !!selectedProvider,
  })

  const discoverMutation = useMutation({
    mutationFn: ({ id, apiKey }: { id: number; apiKey: string }) => providerApi.discover(id, apiKey),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['providerModels', selectedProvider?.id] })
    },
  })

  useEffect(() => {
    if (agent) {
      setName(agent.name)
      setDescription(agent.description)
      setConfig(JSON.stringify(agent.config, null, 2))
      setSystemPrompt(agent.system_prompt || '')
      setModel(agent.model || '')
      setApiUrl(agent.api_url || '')
      setApiKey(agent.api_key || '')
      setEnableBrowsing(!!agent.config?.enable_browsing)
      setEnableFileAccess(!!agent.config?.enable_file_access)
      setFileAccessRoot(agent.config?.file_access_root || './workspace')
      const feishuCfg = agent.config?.feishu || {}
      setEnableFeishu(!!feishuCfg.enabled)
      setFeishuAppId(feishuCfg.app_id || '')
      setFeishuAppSecret(feishuCfg.app_secret || '')

      if (providers) {
        const matched = providers.find(p => p.key === agent.provider) || null
        setSelectedProvider(matched)
      }
    } else {
      setName('')
      setDescription('')
      setConfig('{}')
      setSystemPrompt('')
      setModel('')
      setApiUrl('')
      setApiKey('')
      setSelectedProvider(null)
      setEnableBrowsing(false)
      setEnableFileAccess(false)
      setFileAccessRoot('./workspace')
      setEnableFeishu(false)
      setFeishuAppId('')
      setFeishuAppSecret('')
    }
  }, [agent, providers])

  const handleProviderChange = (providerId: number) => {
    const provider = providers?.find(p => p.id === providerId) || null
    setSelectedProvider(provider)
    if (provider) {
      setApiUrl(provider.base_url || '')
      setApiKey('')
      setModel('')
    }
  }

  const handleModelChange = (value: string) => {
    setModel(value)
  }

  const handleApiUrlChange = (value: string) => {
    setApiUrl(value)
  }

  const handleDiscover = () => {
    if (selectedProvider) {
      discoverMutation.mutate({ id: selectedProvider.id, apiKey })
    }
  }

  // Auto-fill api_url when editing agent and providers loaded
  useEffect(() => {
    if (agent && providers && selectedProvider) {
      // Only auto-fill if current values are empty (newly switched provider)
      if (!apiUrl) {
        setApiUrl(selectedProvider.base_url || '')
      }
    }
  }, [agent, providers, selectedProvider])

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    let parsed: Record<string, unknown> = {}
    try { parsed = JSON.parse(config) } catch { /* ignore */ }
    const feishuConfig = enableFeishu
      ? { feishu: { enabled: true, app_id: feishuAppId, app_secret: feishuAppSecret } }
      : { feishu: { enabled: false } }

    const toolConfig: Record<string, unknown> = {
      ...parsed,
      enable_browsing: enableBrowsing,
      enable_file_access: enableFileAccess,
      ...feishuConfig,
    }
    if (enableFileAccess) {
      toolConfig.file_access_root = fileAccessRoot
    } else {
      delete toolConfig.file_access_root
    }
    onSave({
      name,
      description,
      config: toolConfig,
      system_prompt: systemPrompt,
      model,
      api_url: apiUrl,
      api_key: apiKey,
      provider: selectedProvider?.key || '',
    })
    onClose()
  }

  const hasModels = models && models.length > 0

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50" onClick={onClose}>
      <div className="bg-white rounded-xl p-6 w-full max-w-md shadow-xl max-h-[90vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
        <h2 className="text-lg font-bold mb-4">{agent ? 'Edit Agent' : 'New Agent'}</h2>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700">Name</label>
            <input className="mt-1 w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" value={name} onChange={e => setName(e.target.value)} required />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700">Description</label>
            <textarea className="mt-1 w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" rows={3} value={description} onChange={e => setDescription(e.target.value)} />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700">Provider</label>
            <div className="relative mt-1">
              <select
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm appearance-none bg-white pr-8"
                value={selectedProvider?.id ?? ''}
                onChange={e => handleProviderChange(Number(e.target.value))}
              >
                <option value="">Select a provider</option>
                {providers?.map(p => (
                  <option key={p.id} value={p.id}>{p.name}</option>
                ))}
              </select>
              <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500 pointer-events-none" />
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700">System Prompt</label>
            <textarea className="mt-1 w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" rows={3} value={systemPrompt} onChange={e => setSystemPrompt(e.target.value)} />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700">API URL</label>
            <input className="mt-1 w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" value={apiUrl} onChange={e => handleApiUrlChange(e.target.value)} />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700">API Key</label>
            <input
              type="password"
              className="mt-1 w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
              value={apiKey}
              onChange={e => setApiKey(e.target.value)}
              placeholder={selectedProvider?.key === 'ollama' ? 'optional for ollama' : undefined}
            />
            {selectedProvider?.api_key_env && (
              <p className="mt-1 text-xs text-gray-500">也可通过环境变量 {selectedProvider.api_key_env} 设置</p>
            )}
          </div>
          <div>
            <div className="flex items-center justify-between">
              <label className="block text-sm font-medium text-gray-700">Model</label>
              {selectedProvider && (
                <button
                  type="button"
                  onClick={handleDiscover}
                  disabled={discoverMutation.isPending}
                  className="flex items-center gap-1 text-xs text-gray-600 hover:text-gray-900 disabled:opacity-50"
                >
                  <RefreshCw className={`w-3 h-3 ${discoverMutation.isPending ? 'animate-spin' : ''}`} />
                  Refresh Models
                </button>
              )}
            </div>
            {hasModels ? (
              <div className="relative mt-1">
                <select
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm appearance-none bg-white pr-8"
                  value={model}
                  onChange={e => handleModelChange(e.target.value)}
                >
                  <option value="">Select a model</option>
                  {models.map(m => (
                    <option key={m.id} value={m.model_id}>{m.name || m.model_id}</option>
                  ))}
                </select>
                <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500 pointer-events-none" />
              </div>
            ) : (
              <input className="mt-1 w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" value={model} onChange={e => handleModelChange(e.target.value)} />
            )}
          </div>
          <div className="border border-gray-200 rounded-lg p-3 space-y-3">
            <div className="text-sm font-medium text-gray-900">工具配置</div>
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={enableBrowsing}
                onChange={e => setEnableBrowsing(e.target.checked)}
                className="rounded border-gray-300"
              />
              <span className="text-sm text-gray-700">启用浏览器访问（搜索网页）</span>
            </label>
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={enableFileAccess}
                onChange={e => setEnableFileAccess(e.target.checked)}
                className="rounded border-gray-300"
              />
              <span className="text-sm text-gray-700">启用文件读写</span>
            </label>
            {enableFileAccess && (
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">文件访问根目录</label>
                <input
                  className="w-full border border-gray-300 rounded-lg px-3 py-1.5 text-sm font-mono"
                  value={fileAccessRoot}
                  onChange={e => setFileAccessRoot(e.target.value)}
                  placeholder="./workspace"
                />
                <p className="mt-1 text-xs text-gray-500">Agent 只能访问此目录下的文件，留空则使用默认沙盒 workspace/&#123;agent_id&#125;/</p>
              </div>
            )}
          </div>

          <div className="border border-gray-200 rounded-lg p-3 space-y-3">
            <div className="text-sm font-medium text-gray-900">飞书机器人配置</div>
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
                <div className="space-y-3 pl-6">
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">App ID</label>
                    <input
                      className="w-full border border-gray-300 rounded-lg px-3 py-1.5 text-sm"
                      value={feishuAppId}
                      onChange={e => setFeishuAppId(e.target.value)}
                      placeholder="cli_xxxxxxxxxxxx"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">App Secret</label>
                    <input
                      type="password"
                      className="w-full border border-gray-300 rounded-lg px-3 py-1.5 text-sm"
                      value={feishuAppSecret}
                      onChange={e => setFeishuAppSecret(e.target.value)}
                      placeholder="xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
                    />
                  </div>
                </div>
              </>
            )}
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700">Config (JSON)</label>
            <textarea className="mt-1 w-full border border-gray-300 rounded-lg px-3 py-2 text-sm font-mono" rows={3} value={config} onChange={e => setConfig(e.target.value)} />
            <p className="mt-1 text-xs text-gray-500">工具配置会自动合并到此处，也可手动添加其他配置</p>
          </div>
          {agent && enableFeishu && (
            <FeishuStatus agentId={agent.id} />
          )}
          <div className="flex justify-end gap-2 pt-2">
            <button type="button" onClick={onClose} className="px-4 py-2 text-sm rounded-lg border border-gray-300 hover:bg-gray-50">Cancel</button>
            <button type="submit" className="px-4 py-2 text-sm rounded-lg bg-gray-900 text-white hover:bg-gray-800">Save</button>
          </div>
        </form>
      </div>
    </div>
  )
}
