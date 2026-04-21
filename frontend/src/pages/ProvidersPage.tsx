import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Plug, Pencil, Trash2, ExternalLink } from 'lucide-react'
import { providerApi } from '../api/client'
import type { Provider } from '../types'
import ProviderModal from '../components/ProviderModal'

export default function ProvidersPage() {
  const [modalOpen, setModalOpen] = useState(false)
  const [editing, setEditing] = useState<Provider | null>(null)
  const qc = useQueryClient()

  const { data: providers = [], isLoading } = useQuery({ queryKey: ['providers'], queryFn: providerApi.list })

  const create = useMutation({ mutationFn: providerApi.create, onSuccess: () => qc.invalidateQueries({ queryKey: ['providers'] }) })
  const update = useMutation({ mutationFn: ({ id, data }: { id: number; data: Partial<Provider> }) => providerApi.update(id, data), onSuccess: () => qc.invalidateQueries({ queryKey: ['providers'] }) })
  const remove = useMutation({ mutationFn: providerApi.delete, onSuccess: () => qc.invalidateQueries({ queryKey: ['providers'] }) })

  const handleSave = (data: { name: string; key: string; base_url: string; api_key_env: string; description: string; doc_url: string; is_enabled: boolean; config: Record<string, unknown> }) => {
    if (editing) update.mutate({ id: editing.id, data })
    else create.mutate(data)
  }

  if (isLoading) return <div className="text-gray-500">Loading...</div>

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-2xl font-bold">Providers</h2>
        <button onClick={() => { setEditing(null); setModalOpen(true) }} className="flex items-center gap-2 px-4 py-2 bg-gray-900 text-white rounded-lg text-sm hover:bg-gray-800">
          <Plus size={16} /> New Provider
        </button>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {providers.map(p => (
          <div key={p.id} className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm hover:shadow-md transition-shadow">
            <div className="flex items-start justify-between">
              <div className="flex items-center gap-3">
                <div className={`w-10 h-10 rounded-full flex items-center justify-center ${p.is_builtin ? 'bg-gray-700 text-white' : 'bg-indigo-600 text-white'}`}>
                  <Plug size={20} />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="font-semibold text-gray-900">{p.name}</h3>
                    {p.is_builtin && (
                      <span className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded-full border border-gray-200">Builtin</span>
                    )}
                    {!p.is_enabled && (
                      <span className="text-xs bg-red-50 text-red-600 px-2 py-0.5 rounded-full border border-red-100">Disabled</span>
                    )}
                  </div>
                  <p className="text-sm text-gray-500 line-clamp-1">{p.description || 'No description'}</p>
                </div>
              </div>
              <div className="flex gap-1">
                {!p.is_builtin && (
                  <>
                    <button onClick={() => { setEditing(p); setModalOpen(true) }} className="p-1.5 hover:bg-gray-100 rounded-lg" title="Edit">
                      <Pencil size={16} />
                    </button>
                    <button onClick={() => remove.mutate(p.id)} className="p-1.5 hover:bg-red-50 text-red-600 rounded-lg" title="Delete">
                      <Trash2 size={16} />
                    </button>
                  </>
                )}
              </div>
            </div>
            <div className="mt-3 space-y-1">
              <div className="text-xs text-gray-500">
                <span className="font-medium text-gray-700">Key:</span> {p.key}
              </div>
              <div className="text-xs text-gray-500">
                <span className="font-medium text-gray-700">Base URL:</span> {p.base_url}
              </div>
              {p.doc_url && (
                <div className="text-xs text-gray-500">
                  <a href={p.doc_url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-indigo-600 hover:text-indigo-700">
                    Documentation <ExternalLink size={12} />
                  </a>
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
      {modalOpen && <ProviderModal provider={editing} onClose={() => setModalOpen(false)} onSave={handleSave} />}
    </div>
  )
}
