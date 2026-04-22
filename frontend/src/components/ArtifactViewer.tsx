import { useState } from 'react'
import { X, FileText } from 'lucide-react'

interface Artifact {
  name: string;
  path: string;
  size: number;
}

interface Props {
  artifacts: Artifact[];
  onClose: () => void;
}

export default function ArtifactViewer({ artifacts, onClose }: Props) {
  const [selected, setSelected] = useState<Artifact | null>(null)
  const [content, setContent] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSelect = async (art: Artifact) => {
    setSelected(art)
    setLoading(true)
    try {
      const res = await fetch(`/api/files/artifacts/read?path=${encodeURIComponent(art.path)}`)
      const data = await res.json()
      setContent(data.content || '')
    } catch {
      setContent('Failed to load file')
    }
    setLoading(false)
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50" onClick={onClose}>
      <div className="bg-white rounded-xl w-full max-w-2xl h-[80vh] shadow-xl flex flex-col overflow-hidden" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200">
          <h3 className="font-semibold text-sm">📁 产物文件</h3>
          <button onClick={onClose} className="p-1 hover:bg-gray-100 rounded"><X size={16} /></button>
        </div>
        <div className="flex flex-1 overflow-hidden">
          {/* File tree */}
          <div className="w-48 border-r border-gray-200 overflow-y-auto p-2">
            {artifacts.map(art => (
              <button
                key={art.name}
                onClick={() => handleSelect(art)}
                className={`w-full flex items-center gap-2 px-2 py-1.5 rounded text-xs text-left ${selected?.name === art.name ? 'bg-gray-100 text-gray-900' : 'text-gray-600 hover:bg-gray-50'}`}
              >
                <FileText size={12} />
                <span className="truncate">{art.name}</span>
              </button>
            ))}
            {artifacts.length === 0 && (
              <div className="text-xs text-gray-400 text-center py-4">暂无产物文件</div>
            )}
          </div>
          {/* Content */}
          <div className="flex-1 overflow-y-auto p-4">
            {loading && <div className="flex justify-center mt-10"><span className="w-5 h-5 border-2 border-gray-300 border-t-gray-600 rounded-full animate-spin" /></div>}
            {!loading && selected && (
              <div>
                <div className="text-xs text-gray-400 mb-2">{selected.name} ({(selected.size / 1024).toFixed(1)} KB)</div>
                <pre className="text-xs text-gray-800 bg-gray-50 p-3 rounded-lg whitespace-pre-wrap leading-relaxed">{content}</pre>
              </div>
            )}
            {!selected && !loading && (
              <div className="text-center text-gray-400 text-sm mt-10">选择左侧文件查看内容</div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
