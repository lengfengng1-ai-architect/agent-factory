export interface Agent {
  id: number;
  name: string;
  description: string;
  avatar: string;
  config: Record<string, any>;
  system_prompt: string;
  model: string;
  api_url: string;
  api_key: string;
  provider: string;
  created_at: string;
}

export interface Group {
  id: number;
  name: string;
  description: string;
  agent_ids: number[];
  created_at: string;
}

export type TaskStatus = 'pending' | 'in_progress' | 'completed';

export interface Task {
  id: number;
  title: string;
  description: string;
  status: TaskStatus;
  assignee_type: 'agent' | 'group';
  assignee_id: number;
  created_at: string;
  updated_at?: string;
}
