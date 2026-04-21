import { useState, useEffect, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { ChevronDown, RefreshCw } from 'lucide-react'
import { providerApi } from '../api/client'
import type { Agent, Provider } from '../types'

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
  const [model, setModel] = useState('')
  const [apiUrl, setApiUrl] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [selectedProvider, setSelectedProvider] = useState<Provider | null>(null)

  const modelModified = useRef(false)
  const apiUrlModified = useRef(false)

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
      modelModified.current = true
      apiUrlModified.current = true

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
      modelModified.current = false
      apiUrlModified.current = false
    }
  }, [agent, providers])

  const handleProviderChange = (providerId: number) => {
    const provider = providers?.find(p => p.id === providerId) || null
    setSelectedProvider(provider)
    if (provider) {
      if (!modelModified.current) {
        setModel('')
      }
      if (!apiUrlModified.current) {
        setApiUrl(provider.base_url || '')
      }
    }
  }

  const handleModelChange = (value: string) => {
    setModel(value)
    modelModified.current = true
  }

  const handleApiUrlChange = (value: string) => {
    setApiUrl(value)
    apiUrlModified.current = true
  }

  const handleDiscover = () => {
    if (selectedProvider) {
      discoverMutation.mutate({ id: selectedProvider.id, apiKey })
    }
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    let parsed: Record<string, unknown> = {}
    try { parsed = JSON.parse(config) } catch { /* ignore */ }
    onSave({
      name,
      description,
      config: parsed,
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
            <label className="block text-sm font-medium text-gray-700">Config (JSON)</label>
            <textarea className="mt-1 w-full border border-gray-300 rounded-lg px-3 py-2 text-sm font-mono" rows={4} value={config} onChange={e => setConfig(e.target.value)} />
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <button type="button" onClick={onClose} className="px-4 py-2 text-sm rounded-lg border border-gray-300 hover:bg-gray-50">Cancel</button>
            <button type="submit" className="px-4 py-2 text-sm rounded-lg bg-gray-900 text-white hover:bg-gray-800">Save</button>
          </div>
        </form>
      </div>
    </div>
  )
}
