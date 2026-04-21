import { useState } from 'react'
import AgentsPage from './pages/AgentsPage'
import GroupsPage from './pages/GroupsPage'
import TasksPage from './pages/TasksPage'
import { Bot, Users, ClipboardList } from 'lucide-react'

type Tab = 'agents' | 'groups' | 'tasks'

export default function App() {
  const [tab, setTab] = useState<Tab>('agents')

  return (
    <div className="min-h-screen flex">
      <aside className="w-60 bg-white border-r border-gray-200 flex flex-col">
        <div className="p-6 border-b border-gray-200">
          <h1 className="text-xl font-bold tracking-tight">Agent Factory</h1>
          <p className="text-xs text-gray-500 mt-1">控制中心</p>
        </div>
        <nav className="flex-1 p-3 space-y-1">
          <button
            onClick={() => setTab('agents')}
            className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
              tab === 'agents' ? 'bg-gray-900 text-white' : 'text-gray-700 hover:bg-gray-100'
            }`}
          >
            <Bot size={18} /> Agents
          </button>
          <button
            onClick={() => setTab('groups')}
            className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
              tab === 'groups' ? 'bg-gray-900 text-white' : 'text-gray-700 hover:bg-gray-100'
            }`}
          >
            <Users size={18} /> Groups
          </button>
          <button
            onClick={() => setTab('tasks')}
            className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
              tab === 'tasks' ? 'bg-gray-900 text-white' : 'text-gray-700 hover:bg-gray-100'
            }`}
          >
            <ClipboardList size={18} /> Tasks
          </button>
        </nav>
      </aside>

      <main className="flex-1 p-8 overflow-auto">
        {tab === 'agents' && <AgentsPage />}
        {tab === 'groups' && <GroupsPage />}
        {tab === 'tasks' && <TasksPage />}
      </main>
    </div>
  )
}
