import { useState, useEffect, useRef } from 'react'
import { ChevronDown } from 'lucide-react'
import type { Agent } from '../types'

interface Props {
  agent?: Agent | null
  onClose: () => void
  onSave: (data: { name: string; description: string; config: Record<string, unknown>; system_prompt: string; model: string; api_url: string; api_key: string; provider: string }) => void
}

const PROVIDER_DEFAULTS: Record<string, { api_url: string; model: string }> = {
  kimi: { api_url: 'https://api.kimi.com/coding/', model: 'kimi-latest' },
  ollama: { api_url: 'http://localhost:11434/v1/', model: 'llama3' },
  openai: { api_url: 'https://api.openai.com/v1/', model: 'gpt-4o' },
}

const PROVIDER_OPTIONS = [
  { value: 'kimi', label: 'kimi' },
  { value: 'ollama', label: 'ollama' },
  { value: 'openai', label: 'openai' },
  { value: 'custom', label: 'custom' },
]

export default function AgentModal({ agent, onClose, onSave }: Props) {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [config, setConfig] = useState('{}')
  const [systemPrompt, setSystemPrompt] = useState('')
  const [model, setModel] = useState('kimi-latest')
  const [apiUrl, setApiUrl] = useState('https://api.kimi.com/coding/')
  const [apiKey, setApiKey] = useState('')
  const [provider, setProvider] = useState('kimi')

  const modelModified = useRef(false)
  const apiUrlModified = useRef(false)

  useEffect(() => {
    if (agent) {
      setName(agent.name)
      setDescription(agent.description)
      setConfig(JSON.stringify(agent.config, null, 2))
      setSystemPrompt(agent.system_prompt || '')
      setModel(agent.model || 'kimi-latest')
      setApiUrl(agent.api_url || 'https://api.kimi.com/coding/')
      setApiKey(agent.api_key || '')
      setProvider(agent.provider || 'kimi')
      modelModified.current = true
      apiUrlModified.current = true
    } else {
      setName('')
      setDescription('')
      setConfig('{}')
      setSystemPrompt('')
      setModel('kimi-latest')
      setApiUrl('https://api.kimi.com/coding/')
      setApiKey('')
      setProvider('kimi')
      modelModified.current = false
      apiUrlModified.current = false
    }
  }, [agent])

  const handleProviderChange = (value: string) => {
    setProvider(value)
    if (value !== 'custom' && PROVIDER_DEFAULTS[value]) {
      if (!modelModified.current) {
        setModel(PROVIDER_DEFAULTS[value].model)
      }
      if (!apiUrlModified.current) {
        setApiUrl(PROVIDER_DEFAULTS[value].api_url)
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

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    let parsed: Record<string, unknown> = {}
    try { parsed = JSON.parse(config) } catch { /* ignore */ }
    onSave({ name, description, config: parsed, system_prompt: systemPrompt, model, api_url: apiUrl, api_key: apiKey, provider })
    onClose()
  }

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
                value={provider}
                onChange={e => handleProviderChange(e.target.value)}
              >
                {PROVIDER_OPTIONS.map(opt => (
                  <option key={opt.value} value={opt.value}>{opt.label}</option>
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
            <label className="block text-sm font-medium text-gray-700">Model</label>
            <input className="mt-1 w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" value={model} onChange={e => handleModelChange(e.target.value)} />
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
              placeholder={provider === 'ollama' ? 'optional for ollama' : undefined}
            />
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
