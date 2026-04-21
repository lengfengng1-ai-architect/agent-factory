import { useState, useEffect } from 'react'
import type { Provider } from '../types'
import { AlertTriangle } from 'lucide-react'

interface Props {
  provider?: Provider | null
  onClose: () => void
  onSave: (data: { name: string; key: string; base_url: string; api_key_env: string; description: string; doc_url: string; is_enabled: boolean; config: Record<string, unknown> }) => void
}

export default function ProviderModal({ provider, onClose, onSave }: Props) {
  const [name, setName] = useState('')
  const [key, setKey] = useState('')
  const [baseUrl, setBaseUrl] = useState('')
  const [apiKeyEnv, setApiKeyEnv] = useState('')
  const [description, setDescription] = useState('')
  const [docUrl, setDocUrl] = useState('')
  const [isEnabled, setIsEnabled] = useState(true)
  const [config, setConfig] = useState('{}')

  const isBuiltin = provider?.is_builtin ?? false

  useEffect(() => {
    if (provider) {
      setName(provider.name)
      setKey(provider.key)
      setBaseUrl(provider.base_url)
      setApiKeyEnv(provider.api_key_env)
      setDescription(provider.description)
      setDocUrl(provider.doc_url)
      setIsEnabled(provider.is_enabled)
      setConfig(JSON.stringify(provider.config || {}, null, 2))
    } else {
      setName('')
      setKey('')
      setBaseUrl('')
      setApiKeyEnv('')
      setDescription('')
      setDocUrl('')
      setIsEnabled(true)
      setConfig('{}')
    }
  }, [provider])

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    let parsed: Record<string, unknown> = {}
    try { parsed = JSON.parse(config) } catch { /* ignore */ }
    onSave({ name, key, base_url: baseUrl, api_key_env: apiKeyEnv, description, doc_url: docUrl, is_enabled: isEnabled, config: parsed })
    onClose()
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50" onClick={onClose}>
      <div className="bg-white rounded-xl p-6 w-full max-w-lg shadow-xl max-h-[90vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
        <h2 className="text-lg font-bold mb-4">
          {provider ? 'Edit Provider' : 'New Provider'}
        </h2>
        {isBuiltin && (
          <div className="mb-4 flex items-start gap-2 text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 text-sm">
            <AlertTriangle size={16} className="mt-0.5 shrink-0" />
            <span>This is a built-in provider. Some fields cannot be edited.</span>
          </div>
        )}
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700">Name</label>
            <input className="mt-1 w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" value={name} onChange={e => setName(e.target.value)} required disabled={isBuiltin} />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700">Key</label>
            <input className="mt-1 w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" value={key} onChange={e => setKey(e.target.value)} required disabled={isBuiltin} />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700">Base URL</label>
            <input className="mt-1 w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" value={baseUrl} onChange={e => setBaseUrl(e.target.value)} required />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700">API Key Env Variable</label>
            <input className="mt-1 w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" value={apiKeyEnv} onChange={e => setApiKeyEnv(e.target.value)} />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700">Description</label>
            <textarea className="mt-1 w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" rows={2} value={description} onChange={e => setDescription(e.target.value)} />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700">Documentation URL</label>
            <input className="mt-1 w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" value={docUrl} onChange={e => setDocUrl(e.target.value)} />
          </div>
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="is_enabled"
              checked={isEnabled}
              onChange={e => setIsEnabled(e.target.checked)}
            
              className="rounded border-gray-300"
            />
            <label htmlFor="is_enabled" className="text-sm font-medium text-gray-700">Enabled</label>
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
