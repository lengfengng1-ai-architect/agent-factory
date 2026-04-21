import { useState, useEffect } from 'react'
import type { Agent } from '../types'

interface Props {
  agent?: Agent | null
  onClose: () => void
  onSave: (data: { name: string; description: string; config: Record<string, unknown>; system_prompt: string; model: string; api_url: string; api_key: string }) => void
}

export default function AgentModal({ agent, onClose, onSave }: Props) {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [config, setConfig] = useState('{}')
  const [systemPrompt, setSystemPrompt] = useState('')
  const [model, setModel] = useState('kimi-latest')
  const [apiUrl, setApiUrl] = useState('https://api.kimi.com/coding/')
  const [apiKey, setApiKey] = useState('')

  useEffect(() => {
    if (agent) {
      setName(agent.name)
      setDescription(agent.description)
      setConfig(JSON.stringify(agent.config, null, 2))
      setSystemPrompt(agent.system_prompt || '')
      setModel(agent.model || 'kimi-latest')
      setApiUrl(agent.api_url || 'https://api.kimi.com/coding/')
      setApiKey(agent.api_key || '')
    } else {
      setName('')
      setDescription('')
      setConfig('{}')
      setSystemPrompt('')
      setModel('kimi-latest')
      setApiUrl('https://api.kimi.com/coding/')
      setApiKey('')
    }
  }, [agent])

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    let parsed: Record<string, unknown> = {}
    try { parsed = JSON.parse(config) } catch { /* ignore */ }
    onSave({ name, description, config: parsed, system_prompt: systemPrompt, model, api_url: apiUrl, api_key: apiKey })
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
            <label className="block text-sm font-medium text-gray-700">System Prompt</label>
            <textarea className="mt-1 w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" rows={3} value={systemPrompt} onChange={e => setSystemPrompt(e.target.value)} />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700">Model</label>
            <input className="mt-1 w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" value={model} onChange={e => setModel(e.target.value)} />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700">API URL</label>
            <input className="mt-1 w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" value={apiUrl} onChange={e => setApiUrl(e.target.value)} />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700">API Key</label>
            <input type="password" className="mt-1 w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" value={apiKey} onChange={e => setApiKey(e.target.value)} />
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
