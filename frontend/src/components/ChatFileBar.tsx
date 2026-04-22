import { useRef, useState } from 'react'
import { Paperclip, X, FileText, ChevronDown, Loader2 } from 'lucide-react'
import type { ChatFile } from '../types'

export type FileMode = 'truncate' | 'summary' | 'auto'

interface Props {
  files: ChatFile[]
  fileMode: FileMode
  onUpload: (files: FileList) => void
  onRemove: (fileId: string) => void
  onModeChange: (mode: FileMode) => void
  disabled?: boolean
  uploading?: boolean
}

const MODE_LABELS: Record<FileMode, string> = {
  truncate: '截断',
  summary: '摘要',
  auto: '自动',
}

const MODE_DESC: Record<FileMode, string> = {
  truncate: '保留头尾，适合代码',
  summary: 'LLM 提炼，适合文档',
  auto: '按文件类型自动选择',
}

export default function ChatFileBar({
  files,
  fileMode,
  onUpload,
  onRemove,
  onModeChange,
  disabled,
  uploading,
}: Props) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [showModeMenu, setShowModeMenu] = useState(false)

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      onUpload(e.target.files)
      e.target.value = ''
    }
  }

  const getFileIcon = (name: string) => {
    const ext = name.split('.').pop()?.toLowerCase() || ''
    const codeExts = ['py', 'js', 'ts', 'java', 'go', 'rs', 'c', 'cpp', 'h', 'sql', 'html', 'css', 'json', 'yaml']
    if (codeExts.includes(ext)) {
      return <span className="text-blue-500 text-[10px] font-mono font-bold">{ext}</span>
    }
    if (ext === 'pdf') {
      return <span className="text-red-500 text-[10px] font-bold">PDF</span>
    }
    return <FileText size={12} className="text-gray-400" />
  }

  const formatSize = (size: number) => {
    if (size < 1024) return `${size}B`
    if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)}KB`
    return `${(size / (1024 * 1024)).toFixed(1)}MB`
  }

  return (
    <div className="px-4 py-2 border-t border-gray-100 bg-gray-50/50">
      {/* File list */}
      {files.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mb-2">
          {files.map(file => (
            <div
              key={file.id}
              className="flex items-center gap-1.5 bg-white border border-gray-200 rounded-md px-2 py-1 text-xs group"
              title={`${file.name} (${formatSize(file.size)})`}
            >
              {getFileIcon(file.name)}
              <span className="max-w-[120px] truncate text-gray-700">{file.name}</span>
              <span className="text-gray-400">{formatSize(file.size)}</span>
              <button
                onClick={() => onRemove(file.id)}
                disabled={disabled}
                className="p-0.5 hover:bg-gray-100 rounded text-gray-400 hover:text-red-500 disabled:opacity-50"
              >
                <X size={12} />
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Controls bar */}
      <div className="flex items-center gap-2">
        {/* Upload button */}
        <button
          onClick={() => inputRef.current?.click()}
          disabled={disabled || uploading}
          className="flex items-center gap-1 px-2 py-1 text-xs text-gray-600 hover:text-gray-900 hover:bg-gray-100 rounded-md transition-colors disabled:opacity-50"
          title="上传文件"
        >
          {uploading ? <Loader2 size={14} className="animate-spin" /> : <Paperclip size={14} />}
          <span>{uploading ? '上传中...' : '附件'}</span>
        </button>
        <input
          ref={inputRef}
          type="file"
          multiple
          className="hidden"
          onChange={handleFileSelect}
          disabled={disabled || uploading}
        />

        {/* Mode switcher */}
        <div className="relative">
          <button
            onClick={() => setShowModeMenu(v => !v)}
            disabled={disabled}
            className="flex items-center gap-0.5 px-2 py-1 text-xs text-gray-600 hover:text-gray-900 hover:bg-gray-100 rounded-md transition-colors disabled:opacity-50"
          >
            <span>{MODE_LABELS[fileMode]}</span>
            <ChevronDown size={12} />
          </button>

          {showModeMenu && (
            <>
              <div
                className="fixed inset-0 z-10"
                onClick={() => setShowModeMenu(false)}
              />
              <div className="absolute left-0 bottom-full mb-1 bg-white border border-gray-200 rounded-lg shadow-lg py-1 z-20 min-w-[140px]">
                {(Object.keys(MODE_LABELS) as FileMode[]).map(mode => (
                  <button
                    key={mode}
                    onClick={() => {
                      onModeChange(mode)
                      setShowModeMenu(false)
                    }}
                    className={`w-full text-left px-3 py-1.5 text-xs hover:bg-gray-50 ${
                      fileMode === mode ? 'text-gray-900 font-medium bg-gray-50' : 'text-gray-600'
                    }`}
                  >
                    <div>{MODE_LABELS[mode]}</div>
                    <div className="text-[10px] text-gray-400">{MODE_DESC[mode]}</div>
                  </button>
                ))}
              </div>
            </>
          )}
        </div>

        {files.length > 0 && (
          <span className="text-[10px] text-gray-400">
            {files.length} 个文件
          </span>
        )}
      </div>
    </div>
  )
}
