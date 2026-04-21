# Agent Control Center 实施计划

> **For Hermes:** 使用 subagent-driven-development 技能按任务逐步执行，每个任务完成后必须 `git commit`。

**Goal:** 构建一个全栈 Web 应用，用于管理 Agents、Groups 和 Tasks，支持拖拽 Kanban 看板。

**Architecture:** FastAPI + SQLite 后端提供 REST API，React 19 + Vite + Tailwind 前端消费 API，前后端通过代理直连。数据模型极简：Agent / Group / Task 三张表。

**Tech Stack:**
- 后端：Python 3.11 + FastAPI + SQLAlchemy + Pydantic + SQLite
- 前端：React 19 + TypeScript + Vite + Tailwind CSS v4 + @dnd-kit + Zustand + TanStack Query + Axios + Lucide React
- 环境：uv 管理 Python，npm 管理 Node

**项目根目录：** `/Users/lengfeng/Documents/龙虾/ageng_factory`

---

## Phase 1: 项目脚手架 [已完成]

- [x] 创建项目目录并 `git init`
- [x] 创建 `.gitignore`
- [x] 后端：Python 3.11 虚拟环境（uv venv），安装 fastapi / uvicorn / sqlalchemy / pydantic
- [x] 后端：创建 `database.py`, `models.py`, `schemas.py`, `main.py`
- [x] 后端：创建 `routers/agents.py`, `routers/groups.py`, `routers/tasks.py`（完整 CRUD）
- [x] 前端：`npm create vite@latest frontend -- --template react-ts`
- [x] 前端：安装依赖（tailwindcss, @tanstack/react-query, zustand, axios, @dnd-kit, lucide-react）
- [x] 前端：配置 `vite.config.ts`（tailwind 插件 + proxy `/api` 到 `:8000`）
- [x] 前端：创建 `src/index.css`, `src/types/index.ts`, `src/api/client.ts`, `src/main.tsx`
- [x] 前端：创建 `src/App.tsx` 基础布局（侧边栏导航 + Agents/Groups/Tasks 三个 tab）
- [x] 前端：创建 `src/pages/AgentsPage.tsx`, `GroupsPage.tsx`, `TasksPage.tsx` 空文件

**Commit 指令：**
```bash
cd "/Users/lengfeng/Documents/龙虾/ageng_factory"
git add .
git commit -m "chore: scaffold backend + frontend"
```

---

## Phase 2A: 后端完善与启动

### Task 1: 添加启动脚本与验证后端可运行

**Objective:** 让后端服务能一键启动并健康检查通过。

**Files:**
- Create: `backend/run.sh`
- Modify: `backend/app/main.py`（已存在，确认无误）

**Step 1: 写启动脚本**

Create `backend/run.sh`:
```bash
#!/bin/bash
cd "$(dirname "$0")"
source venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**Step 2: 赋权并启动**

Run:
```bash
chmod +x backend/run.sh
cd backend && ./run.sh &
```

**Step 3: 健康检查**

Run:
```bash
curl http://localhost:8000/api/health
```
Expected: `{"status":"ok"}`

**Step 4: Commit**

```bash
git add backend/run.sh
git commit -m "feat(backend): add run script and verify health check"
```

---

### Task 2: 后端添加 CORS 支持并验证 API 文档

**Objective:** 确认 Swagger UI 可访问，API 接口完整。

**Step 1: 确认 CORS**

`backend/app/main.py` 中已包含 CORS 中间件（允许 `localhost:5173`），无需修改。

**Step 2: 验证 Swagger**

浏览器打开 `http://localhost:8000/docs`，应看到 Agents / Groups / Tasks 三个标签页。

**Step 3: 用 curl 测试 Agent CRUD**

```bash
curl -X POST http://localhost:8000/api/agents/ -H "Content-Type: application/json" -d '{"name":"TestAgent","description":"desc","config":{"model":"gpt-4"}}'
curl http://localhost:8000/api/agents/
```
Expected: 返回包含 TestAgent 的列表。

**Step 4: Commit**

```bash
git add -A
git commit -m "feat(backend): verify CORS and Swagger docs"
```

---

## Phase 2B: 前端页面开发（可跟 Phase 2A 并行）

### Task 3: Agents 页面 — 列表与增删改查

**Objective:** 完成 Agents 的展示、新建、编辑、删除。

**Files:**
- Modify: `frontend/src/pages/AgentsPage.tsx`
- Create: `frontend/src/components/AgentCard.tsx`
- Create: `frontend/src/components/AgentModal.tsx`

**Step 1: 写 AgentCard 组件**

Create `frontend/src/components/AgentCard.tsx`:
```tsx
import type { Agent } from '../types'
import { Bot, Pencil, Trash2 } from 'lucide-react'

interface Props {
  agent: Agent
  onEdit: (agent: Agent) => void
  onDelete: (id: number) => void
}

export default function AgentCard({ agent, onEdit, onDelete }: Props) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm hover:shadow-md transition-shadow">
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-full bg-gray-900 text-white flex items-center justify-center">
            <Bot size={20} />
          </div>
          <div>
            <h3 className="font-semibold text-gray-900">{agent.name}</h3>
            <p className="text-sm text-gray-500 line-clamp-1">{agent.description}</p>
          </div>
        </div>
        <div className="flex gap-1">
          <button onClick={() => onEdit(agent)} className="p-1.5 hover:bg-gray-100 rounded-lg"><Pencil size={16} /></button>
          <button onClick={() => onDelete(agent.id)} className="p-1.5 hover:bg-red-50 text-red-600 rounded-lg"><Trash2 size={16} /></button>
        </div>
      </div>
      <div className="mt-3 text-xs text-gray-400">ID: {agent.id}</div>
    </div>
  )
}
```

**Step 2: 写 AgentModal 组件**

Create `frontend/src/components/AgentModal.tsx`:
```tsx
import { useState, useEffect } from 'react'
import type { Agent } from '../types'

interface Props {
  agent?: Agent | null
  onClose: () => void
  onSave: (data: { name: string; description: string; config: Record<string, any> }) => void
}

export default function AgentModal({ agent, onClose, onSave }: Props) {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [config, setConfig] = useState('{}')

  useEffect(() => {
    if (agent) {
      setName(agent.name)
      setDescription(agent.description)
      setConfig(JSON.stringify(agent.config, null, 2))
    } else {
      setName('')
      setDescription('')
      setConfig('{}')
    }
  }, [agent])

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    let parsed = {}
    try { parsed = JSON.parse(config) } catch { /* ignore */ }
    onSave({ name, description, config: parsed })
    onClose()
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50" onClick={onClose}>
      <div className="bg-white rounded-xl p-6 w-full max-w-md shadow-xl" onClick={e => e.stopPropagation()}>
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
```

**Step 3: 写 AgentsPage**

Modify `frontend/src/pages/AgentsPage.tsx`:
```tsx
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus } from 'lucide-react'
import { agentApi } from '../api/client'
import type { Agent } from '../types'
import AgentCard from '../components/AgentCard'
import AgentModal from '../components/AgentModal'

export default function AgentsPage() {
  const [modalOpen, setModalOpen] = useState(false)
  const [editing, setEditing] = useState<Agent | null>(null)
  const qc = useQueryClient()

  const { data: agents = [], isLoading } = useQuery({ queryKey: ['agents'], queryFn: agentApi.list })

  const create = useMutation({ mutationFn: agentApi.create, onSuccess: () => qc.invalidateQueries({ queryKey: ['agents'] }) })
  const update = useMutation({ mutationFn: ({ id, data }: { id: number; data: Partial<Agent> }) => agentApi.update(id, data), onSuccess: () => qc.invalidateQueries({ queryKey: ['agents'] }) })
  const remove = useMutation({ mutationFn: agentApi.delete, onSuccess: () => qc.invalidateQueries({ queryKey: ['agents'] }) })

  const handleSave = (data: { name: string; description: string; config: Record<string, any> }) => {
    if (editing) update.mutate({ id: editing.id, data })
    else create.mutate(data)
  }

  if (isLoading) return <div className="text-gray-500">Loading...</div>

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-2xl font-bold">Agents</h2>
        <button onClick={() => { setEditing(null); setModalOpen(true) }} className="flex items-center gap-2 px-4 py-2 bg-gray-900 text-white rounded-lg text-sm hover:bg-gray-800">
          <Plus size={16} /> New Agent
        </button>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {agents.map(a => (
          <AgentCard key={a.id} agent={a} onEdit={a => { setEditing(a); setModalOpen(true) }} onDelete={id => remove.mutate(id)} />
        ))}
      </div>
      {modalOpen && <AgentModal agent={editing} onClose={() => setModalOpen(false)} onSave={handleSave} />}
    </div>
  )
}
```

**Step 4: 验证 Agents 页面**

启动后端和前端，打开 `http://localhost:5173`，切换到 Agents tab，测试新建、编辑、删除。

**Step 5: Commit**

```bash
git add frontend/src/components/AgentCard.tsx frontend/src/components/AgentModal.tsx frontend/src/pages/AgentsPage.tsx
git commit -m "feat(frontend): agents list with CRUD modal"
```

---

### Task 4: Groups 页面 — 列表、创建组、选择 Agent 入组

**Objective:** 完成 Group 的展示、新建、编辑成员、删除。

**Files:**
- Modify: `frontend/src/pages/GroupsPage.tsx`
- Create: `frontend/src/components/GroupModal.tsx`

**Step 1: 写 GroupModal**

Create `frontend/src/components/GroupModal.tsx`:
```tsx
import { useState, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import type { Group, Agent } from '../types'
import { agentApi } from '../api/client'

interface Props {
  group?: Group | null
  onClose: () => void
  onSave: (data: { name: string; description: string; agent_ids: number[] }) => void
}

export default function GroupModal({ group, onClose, onSave }: Props) {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [selected, setSelected] = useState<number[]>([])
  const { data: agents = [] } = useQuery({ queryKey: ['agents'], queryFn: agentApi.list })

  useEffect(() => {
    if (group) {
      setName(group.name)
      setDescription(group.description)
      setSelected(group.agent_ids || [])
    } else {
      setName('')
      setDescription('')
      setSelected([])
    }
  }, [group])

  const toggle = (id: number) => {
    setSelected(prev => prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id])
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50" onClick={onClose}>
      <div className="bg-white rounded-xl p-6 w-full max-w-lg shadow-xl" onClick={e => e.stopPropagation()}>
        <h2 className="text-lg font-bold mb-4">{group ? 'Edit Group' : 'New Group'}</h2>
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700">Name</label>
            <input className="mt-1 w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" value={name} onChange={e => setName(e.target.value)} required />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700">Description</label>
            <textarea className="mt-1 w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" rows={2} value={description} onChange={e => setDescription(e.target.value)} />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">Select Agents</label>
            <div className="border border-gray-200 rounded-lg max-h-48 overflow-y-auto p-2 space-y-1">
              {agents.map(a => (
                <label key={a.id} className="flex items-center gap-2 px-2 py-1.5 hover:bg-gray-50 rounded cursor-pointer">
                  <input type="checkbox" checked={selected.includes(a.id)} onChange={() => toggle(a.id)} />
                  <span className="text-sm">{a.name}</span>
                </label>
              ))}
            </div>
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <button onClick={onClose} className="px-4 py-2 text-sm rounded-lg border border-gray-300 hover:bg-gray-50">Cancel</button>
            <button onClick={() => { onSave({ name, description, agent_ids: selected }); onClose() }} className="px-4 py-2 text-sm rounded-lg bg-gray-900 text-white hover:bg-gray-800">Save</button>
          </div>
        </div>
      </div>
    </div>
  )
}
```

**Step 2: 写 GroupsPage**

Modify `frontend/src/pages/GroupsPage.tsx`:
```tsx
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Users, Pencil, Trash2 } from 'lucide-react'
import { groupApi, agentApi } from '../api/client'
import type { Group } from '../types'
import GroupModal from '../components/GroupModal'

export default function GroupsPage() {
  const [modalOpen, setModalOpen] = useState(false)
  const [editing, setEditing] = useState<Group | null>(null)
  const qc = useQueryClient()

  const { data: groups = [] } = useQuery({ queryKey: ['groups'], queryFn: groupApi.list })
  const { data: agents = [] } = useQuery({ queryKey: ['agents'], queryFn: agentApi.list })

  const create = useMutation({ mutationFn: groupApi.create, onSuccess: () => qc.invalidateQueries({ queryKey: ['groups'] }) })
  const update = useMutation({ mutationFn: ({ id, data }: { id: number; data: Partial<Group> }) => groupApi.update(id, data), onSuccess: () => qc.invalidateQueries({ queryKey: ['groups'] }) })
  const remove = useMutation({ mutationFn: groupApi.delete, onSuccess: () => qc.invalidateQueries({ queryKey: ['groups'] }) })

  const agentMap = new Map(agents.map(a => [a.id, a.name]))

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-2xl font-bold">Groups</h2>
        <button onClick={() => { setEditing(null); setModalOpen(true) }} className="flex items-center gap-2 px-4 py-2 bg-gray-900 text-white rounded-lg text-sm hover:bg-gray-800">
          <Plus size={16} /> New Group
        </button>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {groups.map(g => (
          <div key={g.id} className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
            <div className="flex items-start justify-between">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-full bg-blue-600 text-white flex items-center justify-center">
                  <Users size={20} />
                </div>
                <div>
                  <h3 className="font-semibold text-gray-900">{g.name}</h3>
                  <p className="text-sm text-gray-500">{g.description}</p>
                </div>
              </div>
              <div className="flex gap-1">
                <button onClick={() => { setEditing(g); setModalOpen(true) }} className="p-1.5 hover:bg-gray-100 rounded-lg"><Pencil size={16} /></button>
                <button onClick={() => remove.mutate(g.id)} className="p-1.5 hover:bg-red-50 text-red-600 rounded-lg"><Trash2 size={16} /></button>
              </div>
            </div>
            <div className="mt-3">
              <p className="text-xs font-medium text-gray-500 mb-1">Members ({g.agent_ids?.length || 0})</p>
              <div className="flex flex-wrap gap-1">
                {g.agent_ids?.map(id => (
                  <span key={id} className="text-xs bg-gray-100 text-gray-700 px-2 py-0.5 rounded-full">{agentMap.get(id) || `ID:${id}`}</span>
                ))}
              </div>
            </div>
          </div>
        ))}
      </div>
      {modalOpen && <GroupModal group={editing} onClose={() => setModalOpen(false)} onSave={data => {
        if (editing) update.mutate({ id: editing.id, data })
        else create.mutate(data)
      }} />}
    </div>
  )
}
```

**Step 3: Commit**

```bash
git add frontend/src/components/GroupModal.tsx frontend/src/pages/GroupsPage.tsx
git commit -m "feat(frontend): groups page with agent selection"
```

---

## Phase 3: Tasks Kanban + 拖拽

### Task 5: Tasks 页面 — Kanban 三列 + 拖拽改状态

**Objective:** 实现未做 / 进行中 / 已完成 三列看板，支持拖拽任务卡片改变状态。

**Files:**
- Modify: `frontend/src/pages/TasksPage.tsx`
- Create: `frontend/src/components/TaskCard.tsx`
- Create: `frontend/src/components/TaskModal.tsx`

**Step 1: 写 TaskModal**

Create `frontend/src/components/TaskModal.tsx`:
```tsx
import { useState, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import type { Task, TaskStatus } from '../types'
import { agentApi, groupApi } from '../api/client'

interface Props {
  task?: Task | null
  onClose: () => void
  onSave: (data: { title: string; description: string; status: TaskStatus; assignee_type: 'agent' | 'group'; assignee_id: number }) => void
}

export default function TaskModal({ task, onClose, onSave }: Props) {
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [status, setStatus] = useState<TaskStatus>('pending')
  const [assigneeType, setAssigneeType] = useState<'agent' | 'group'>('agent')
  const [assigneeId, setAssigneeId] = useState<number>(0)

  const { data: agents = [] } = useQuery({ queryKey: ['agents'], queryFn: agentApi.list })
  const { data: groups = [] } = useQuery({ queryKey: ['groups'], queryFn: groupApi.list })

  useEffect(() => {
    if (task) {
      setTitle(task.title)
      setDescription(task.description)
      setStatus(task.status)
      setAssigneeType(task.assignee_type)
      setAssigneeId(task.assignee_id)
    } else {
      setTitle('')
      setDescription('')
      setStatus('pending')
      setAssigneeType('agent')
      setAssigneeId(agents[0]?.id || 0)
    }
  }, [task, agents])

  const candidates = assigneeType === 'agent' ? agents : groups

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50" onClick={onClose}>
      <div className="bg-white rounded-xl p-6 w-full max-w-md shadow-xl" onClick={e => e.stopPropagation()}>
        <h2 className="text-lg font-bold mb-4">{task ? 'Edit Task' : 'New Task'}</h2>
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700">Title</label>
            <input className="mt-1 w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" value={title} onChange={e => setTitle(e.target.value)} required />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700">Description</label>
            <textarea className="mt-1 w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" rows={3} value={description} onChange={e => setDescription(e.target.value)} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium text-gray-700">Assignee Type</label>
              <select className="mt-1 w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" value={assigneeType} onChange={e => { setAssigneeType(e.target.value as any); setAssigneeId(0) }}>
                <option value="agent">Agent</option>
                <option value="group">Group</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700">Assignee</label>
              <select className="mt-1 w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" value={assigneeId} onChange={e => setAssigneeId(Number(e.target.value))}>
                {candidates.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            </div>
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <button onClick={onClose} className="px-4 py-2 text-sm rounded-lg border border-gray-300 hover:bg-gray-50">Cancel</button>
            <button onClick={() => { onSave({ title, description, status, assignee_type: assigneeType, assignee_id: assigneeId }); onClose() }} className="px-4 py-2 text-sm rounded-lg bg-gray-900 text-white hover:bg-gray-800">Save</button>
          </div>
        </div>
      </div>
    </div>
  )
}
```

**Step 2: 写 TaskCard**

Create `frontend/src/components/TaskCard.tsx`:
```tsx
import { useDraggable } from '@dnd-kit/core'
import type { Task } from '../types'
import { GripVertical } from 'lucide-react'

interface Props {
  task: Task
  onEdit: (task: Task) => void
}

export default function TaskCard({ task, onEdit }: Props) {
  const { attributes, listeners, setNodeRef, transform } = useDraggable({ id: `task-${task.id}`, data: task })
  const style = transform ? { transform: `translate3d(${transform.x}px, ${transform.y}px, 0)` } : undefined

  const statusColor = {
    pending: 'border-gray-200',
    in_progress: 'border-blue-300',
    completed: 'border-green-300',
  }[task.status]

  return (
    <div ref={setNodeRef} style={style} className={`bg-white rounded-lg border ${statusColor} p-3 shadow-sm cursor-pointer hover:shadow-md transition-shadow`} onClick={() => onEdit(task)}>
      <div className="flex items-start gap-2">
        <div {...listeners} {...attributes} className="mt-0.5 text-gray-400 hover:text-gray-600 cursor-grab active:cursor-grabbing">
          <GripVertical size={16} />
        </div>
        <div className="flex-1 min-w-0">
          <h4 className="text-sm font-medium text-gray-900 truncate">{task.title}</h4>
          <p className="text-xs text-gray-500 mt-0.5 line-clamp-2">{task.description}</p>
          <div className="mt-2 flex items-center gap-2">
            <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${
              task.assignee_type === 'agent' ? 'bg-purple-50 text-purple-700' : 'bg-blue-50 text-blue-700'
            }`}>
              {task.assignee_type === 'agent' ? 'AGENT' : 'GROUP'}
            </span>
            <span className="text-[10px] text-gray-400">ID:{task.assignee_id}</span>
          </div>
        </div>
      </div>
    </div>
  )
}
```

**Step 3: 写 TasksPage（Kanban + DndContext）**

Modify `frontend/src/pages/TasksPage.tsx`:
```tsx
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { DndContext, type DragEndEvent, PointerSensor, useSensor, useSensors } from '@dnd-kit/core'
import { Plus } from 'lucide-react'
import { taskApi } from '../api/client'
import type { Task, TaskStatus } from '../types'
import TaskCard from '../components/TaskCard'
import TaskModal from '../components/TaskModal'

const COLUMNS: { id: TaskStatus; title: string; bg: string }[] = [
  { id: 'pending', title: 'To Do', bg: 'bg-gray-50' },
  { id: 'in_progress', title: 'In Progress', bg: 'bg-blue-50/50' },
  { id: 'completed', title: 'Done', bg: 'bg-green-50/50' },
]

export default function TasksPage() {
  const [modalOpen, setModalOpen] = useState(false)
  const [editing, setEditing] = useState<Task | null>(null)
  const qc = useQueryClient()

  const { data: tasks = [] } = useQuery({ queryKey: ['tasks'], queryFn: taskApi.list })

  const create = useMutation({ mutationFn: taskApi.create, onSuccess: () => qc.invalidateQueries({ queryKey: ['tasks'] }) })
  const update = useMutation({ mutationFn: ({ id, data }: { id: number; data: Partial<Task> }) => taskApi.update(id, data), onSuccess: () => qc.invalidateQueries({ queryKey: ['tasks'] }) })
  const remove = useMutation({ mutationFn: taskApi.delete, onSuccess: () => qc.invalidateQueries({ queryKey: ['tasks'] }) })

  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 5 } }))

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event
    if (!over) return
    const taskId = Number(String(active.id).replace('task-', ''))
    const newStatus = String(over.id) as TaskStatus
    const task = tasks.find(t => t.id === taskId)
    if (task && task.status !== newStatus) {
      update.mutate({ id: taskId, data: { status: newStatus } })
    }
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-2xl font-bold">Tasks</h2>
        <button onClick={() => { setEditing(null); setModalOpen(true) }} className="flex items-center gap-2 px-4 py-2 bg-gray-900 text-white rounded-lg text-sm hover:bg-gray-800">
          <Plus size={16} /> New Task
        </button>
      </div>

      <DndContext sensors={sensors} onDragEnd={handleDragEnd}>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {COLUMNS.map(col => {
            const colTasks = tasks.filter(t => t.status === col.id)
            return (
              <div key={col.id} id={col.id} className={`${col.bg} rounded-xl border border-gray-200 p-3 min-h-[300px]`} data-status={col.id}>
                <div className="flex items-center justify-between mb-3 px-1">
                  <h3 className="text-sm font-semibold text-gray-700">{col.title}</h3>
                  <span className="text-xs bg-white text-gray-500 px-2 py-0.5 rounded-full border border-gray-200">{colTasks.length}</span>
                </div>
                <div className="space-y-2">
                  {colTasks.map(task => (
                    <TaskCard key={task.id} task={task} onEdit={t => { setEditing(t); setModalOpen(true) }} />
                  ))}
                </div>
              </div>
            )
          })}
        </div>
      </DndContext>

      {modalOpen && <TaskModal task={editing} onClose={() => setModalOpen(false)} onSave={data => {
        if (editing) update.mutate({ id: editing.id, data })
        else create.mutate(data)
      }} />}
    </div>
  )
}
```

**Step 4: Commit**

```bash
git add frontend/src/components/TaskCard.tsx frontend/src/components/TaskModal.tsx frontend/src/pages/TasksPage.tsx
git commit -m "feat(frontend): tasks kanban board with drag-and-drop"
```

---

## Phase 4: 收尾与验证

### Task 6: 添加 README 与启动说明

**Objective:** 项目可交接，任何人能一键启动。

**Files:**
- Modify: `README.md`（根目录）

**Step 1: 写 README**

Create `README.md`:
```markdown
# Agent Control Center

管理 Agents、Groups 和 Tasks 的全栈控制台。

## 启动

### 后端
```bash
cd backend
source venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

### 前端
```bash
cd frontend
npm run dev
```

打开 http://localhost:5173

## 功能
- Agents：增删改查，JSON 配置
- Groups：多选 Agent 建组
- Tasks：Kanban 看板，拖拽改状态，分配给 Agent 或 Group
```

**Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add README with startup instructions"
```

---

## 子代理分派策略

- **子代理 A（后端）：** 执行 Phase 2A（Task 1-2）
- **子代理 B（前端）：** 执行 Phase 2B + Phase 3（Task 3-5）
- **最终验收：** 前后端都完成后，执行 Phase 4（Task 6）并做一次全量联调

每个子代理拿到任务后，按顺序执行，每完成一个 Task 必须 `git commit`。工作目录固定为 `/Users/lengfeng/Documents/龙虾/ageng_factory`。
