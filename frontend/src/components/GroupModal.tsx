import { useState, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import type { Group } from '../types'
import { agentApi } from '../api/client'

interface Props {
  group?: Group | null
  onClose: () => void
  onSave: (data: { name: string; description: string; agent_ids: number[]; chat_type: string; config?: Record<string, any> }) => void
}

interface DebateConfig {
  pro_agent_ids: number[]
  con_agent_ids: number[]
  rounds: number
  summary_agent_id?: number
}

interface ModeratorConfig {
  moderator_id?: number
}

export default function GroupModal({ group, onClose, onSave }: Props) {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [selectedAgentIds, setSelectedAgentIds] = useState<number[]>([])
  const [chatType, setChatType] = useState('parallel')
  const [debateConfig, setDebateConfig] = useState<DebateConfig>({
    pro_agent_ids: [],
    con_agent_ids: [],
    rounds: 3,
    summary_agent_id: undefined,
  })
  const [moderatorConfig, setModeratorConfig] = useState<ModeratorConfig>({
    moderator_id: undefined,
  })

  const { data: agents = [] } = useQuery({ queryKey: ['agents'], queryFn: agentApi.list })

  useEffect(() => {
    if (group) {
      setName(group.name)
      setDescription(group.description)
      setSelectedAgentIds(group.agent_ids || [])
      setChatType(group.chat_type || 'parallel')
      const dCfg = group.config?.debate as DebateConfig | undefined
      if (dCfg) {
        setDebateConfig({
          pro_agent_ids: dCfg.pro_agent_ids || [],
          con_agent_ids: dCfg.con_agent_ids || [],
          rounds: dCfg.rounds ?? 3,
          summary_agent_id: dCfg.summary_agent_id,
        })
      }
      const mCfg = group.config?.moderator as ModeratorConfig | undefined
      if (mCfg) {
        setModeratorConfig({ moderator_id: mCfg.moderator_id })
      }
    } else {
      setName('')
      setDescription('')
      setSelectedAgentIds([])
      setChatType('parallel')
      setDebateConfig({ pro_agent_ids: [], con_agent_ids: [], rounds: 3, summary_agent_id: undefined })
      setModeratorConfig({ moderator_id: undefined })
    }
  }, [group])

  // Auto-init debate config when agents selected and switching to debate
  useEffect(() => {
    if (chatType !== 'debate') return
    if (selectedAgentIds.length < 2) return
    setDebateConfig(prev => {
      if (prev.pro_agent_ids.length > 0 || prev.con_agent_ids.length > 0) return prev
      return {
        pro_agent_ids: [selectedAgentIds[0]],
        con_agent_ids: selectedAgentIds.slice(1),
        rounds: 3,
        summary_agent_id: selectedAgentIds[0],
      }
    })
  }, [chatType, selectedAgentIds])

  // Auto-init moderator config when switching to moderator
  useEffect(() => {
    if (chatType !== 'moderator') return
    if (selectedAgentIds.length === 0) return
    setModeratorConfig(prev => {
      if (prev.moderator_id && selectedAgentIds.includes(prev.moderator_id)) return prev
      return { moderator_id: selectedAgentIds[0] }
    })
  }, [chatType, selectedAgentIds])

  const toggleAgent = (id: number) => {
    setSelectedAgentIds(prev => {
      const next = prev.includes(id) ? prev.filter(i => i !== id) : [...prev, id]
      // Remove from debate config if agent is deselected
      if (!next.includes(id)) {
        setDebateConfig(d => ({
          ...d,
          pro_agent_ids: d.pro_agent_ids.filter(aid => aid !== id),
          con_agent_ids: d.con_agent_ids.filter(aid => aid !== id),
          summary_agent_id: d.summary_agent_id === id ? undefined : d.summary_agent_id,
        }))
      }
      return next
    })
  }

  const setAgentSide = (id: number, side: 'pro' | 'con' | 'none') => {
    setDebateConfig(prev => {
      const next: DebateConfig = {
        ...prev,
        pro_agent_ids: prev.pro_agent_ids.filter(aid => aid !== id),
        con_agent_ids: prev.con_agent_ids.filter(aid => aid !== id),
      }
      if (side === 'pro') next.pro_agent_ids.push(id)
      if (side === 'con') next.con_agent_ids.push(id)
      return next
    })
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    const payload: Parameters<Props['onSave']>[0] = {
      name,
      description,
      agent_ids: selectedAgentIds,
      chat_type: chatType,
    }
    if (chatType === 'debate') {
      payload.config = {
        ...(group?.config || {}),
        debate: debateConfig,
      }
    }
    onSave(payload)
    onClose()
  }

  const selectedAgents = agents.filter(a => selectedAgentIds.includes(a.id))

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50" onClick={onClose}>
      <div className="bg-white rounded-xl p-6 w-full max-w-lg shadow-xl max-h-[90vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
        <h2 className="text-lg font-bold mb-4">{group ? 'Edit Group' : 'New Group'}</h2>
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
            <label className="block text-sm font-medium text-gray-700 mb-2">Chat Mode</label>
            <div className="space-y-2">
              {[
                { key: 'parallel', label: '并行咨询', desc: '所有 Agent 同时回答，快速收集多方意见' },
                { key: 'brainstorm', label: '头脑风暴', desc: 'Agent 依次发言，互相激发创意' },
                { key: 'debate', label: '辩论模式', desc: '正反方 Agent 对抗讨论，可配置阵营与回合' },
                { key: 'moderator', label: '主持人模式', desc: '主持人 Agent 分派问题并汇总' },
              ].map(opt => (
                <label key={opt.key} className={`flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${chatType === opt.key ? 'border-gray-900 bg-gray-50' : 'border-gray-200 hover:border-gray-300'}`}>
                  <input
                    type="radio"
                    name="chat_type"
                    value={opt.key}
                    checked={chatType === opt.key}
                    onChange={() => setChatType(opt.key)}
                    className="mt-1"
                  />
                  <div>
                    <div className="text-sm font-medium text-gray-900">{opt.label}</div>
                    <div className="text-xs text-gray-500">{opt.desc}</div>
                  </div>
                </label>
              ))}
            </div>
          </div>

          {/* Debate Configuration */}
          {chatType === 'debate' && (
            <div className="space-y-3 border border-gray-200 rounded-lg p-3 bg-gray-50">
              <div className="text-sm font-medium text-gray-900">辩论配置</div>

              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">阵营分配（已选 Agent）</label>
                {selectedAgents.length === 0 && (
                  <div className="text-xs text-gray-400">请先选择下方的 Agent</div>
                )}
                <div className="space-y-1.5">
                  {selectedAgents.map(a => {
                    let side: 'pro' | 'con' | 'none' = 'none'
                    if (debateConfig.pro_agent_ids.includes(a.id)) side = 'pro'
                    else if (debateConfig.con_agent_ids.includes(a.id)) side = 'con'
                    return (
                      <div key={a.id} className="flex items-center justify-between bg-white px-2 py-1.5 rounded border border-gray-200">
                        <span className="text-sm text-gray-700">{a.name}</span>
                        <div className="flex gap-1">
                          {[
                            { key: 'pro' as const, label: '正方', className: 'bg-red-50 text-red-700 border-red-200' },
                            { key: 'con' as const, label: '反方', className: 'bg-blue-50 text-blue-700 border-blue-200' },
                            { key: 'none' as const, label: '未分配', className: 'bg-gray-50 text-gray-500 border-gray-200' },
                          ].map(opt => (
                            <button
                              key={opt.key}
                              type="button"
                              onClick={() => setAgentSide(a.id, opt.key)}
                              className={`text-xs px-2 py-0.5 rounded border transition-colors ${side === opt.key ? opt.className : 'border-transparent text-gray-400 hover:text-gray-600'}`}
                            >
                              {opt.label}
                            </button>
                          ))}
                        </div>
                      </div>
                    )
                  })}
                </div>
              </div>

              <div className="flex gap-3">
                <div className="flex-1">
                  <label className="block text-xs font-medium text-gray-600 mb-1">回合数</label>
                  <input
                    type="number"
                    min={1}
                    max={10}
                    value={debateConfig.rounds}
                    onChange={e => setDebateConfig(prev => ({ ...prev, rounds: Math.max(1, Math.min(10, Number(e.target.value))) }))}
                    className="w-full border border-gray-300 rounded-lg px-3 py-1.5 text-sm"
                  />
                </div>
                <div className="flex-1">
                  <label className="block text-xs font-medium text-gray-600 mb-1">总结 Agent</label>
                  <select
                    value={debateConfig.summary_agent_id ?? ''}
                    onChange={e => setDebateConfig(prev => ({ ...prev, summary_agent_id: e.target.value ? Number(e.target.value) : undefined }))}
                    className="w-full border border-gray-300 rounded-lg px-3 py-1.5 text-sm"
                  >
                    <option value="">不总结</option>
                    {selectedAgents.map(a => (
                      <option key={a.id} value={a.id}>{a.name}</option>
                    ))}
                  </select>
                </div>
              </div>
            </div>
          )}

          {chatType === 'moderator' && (
            <div className="space-y-3 border border-gray-200 rounded-lg p-3 bg-gray-50">
              <div className="text-sm font-medium text-gray-900">主持人配置</div>

              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">指定主持人</label>
                {selectedAgents.length === 0 && (
                  <div className="text-xs text-gray-400">请先选择下方的 Agent</div>
                )}
                {selectedAgents.length > 0 && (
                  <select
                    value={moderatorConfig.moderator_id ?? ''}
                    onChange={e => setModeratorConfig({ moderator_id: e.target.value ? Number(e.target.value) : undefined })}
                    className="w-full border border-gray-300 rounded-lg px-3 py-1.5 text-sm"
                  >
                    {selectedAgents.map(a => (
                      <option key={a.id} value={a.id}>{a.name}</option>
                    ))}
                  </select>
                )}
              </div>

              {selectedAgents.length > 0 && (
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">专家 Agent</label>
                  <div className="space-y-1.5">
                    {selectedAgents.filter(a => a.id !== moderatorConfig.moderator_id).map(a => (
                      <div key={a.id} className="flex items-center justify-between bg-white px-2 py-1.5 rounded border border-gray-200">
                        <span className="text-sm text-gray-700">{a.name}</span>
                        <span className="text-xs bg-blue-50 text-blue-700 px-2 py-0.5 rounded border border-blue-200">专家</span>
                      </div>
                    ))}
                    {selectedAgents.filter(a => a.id !== moderatorConfig.moderator_id).length === 0 && (
                      <div className="text-xs text-gray-400">请至少选择一个非主持人的 Agent 作为专家</div>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">Agents</label>
            <div className="space-y-2 max-h-48 overflow-y-auto border border-gray-200 rounded-lg p-2">
              {agents.map(a => (
                <label key={a.id} className="flex items-center gap-2 cursor-pointer hover:bg-gray-50 p-1 rounded">
                  <input
                    type="checkbox"
                    checked={selectedAgentIds.includes(a.id)}
                    onChange={() => toggleAgent(a.id)}
                    className="rounded border-gray-300"
                  />
                  <span className="text-sm text-gray-700">{a.name}</span>
                </label>
              ))}
            </div>
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
