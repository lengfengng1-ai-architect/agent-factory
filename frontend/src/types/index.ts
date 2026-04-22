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
  chat_type: string;
  config?: Record<string, any>;
  file_root_dir?: string;
  created_at: string;
}

export type TaskStatus = 'pending' | 'in_progress' | 'completed';

export interface Task {
  id: number;
  title: string;
  description: string;
  status: TaskStatus;
  assignee_type: 'agent' | 'group';
  assignee_id: number | null;
  result?: string;
  auto_execute?: boolean;
  progress?: number;
  file_root_dir?: string;
  created_at: string;
  updated_at?: string;
}

export interface Provider {
  id: number;
  name: string;
  key: string;
  base_url: string;
  api_key_env: string;
  description: string;
  doc_url: string;
  is_builtin: boolean;
  is_enabled: boolean;
  config: Record<string, any>;
  created_at: string;
}

export interface ProviderModel {
  id: number;
  provider_id: number;
  model_id: string;
  name: string;
  context_window: number | null;
  created_at: string;
}

export interface ChatFile {
  id: string;
  name: string;
  size: number;
  type: string;
  timestamp: string;
}

export interface FileSummary {
  id: number;
  content_hash: string;
  file_name: string;
  file_ext: string;
  file_size: number;
  char_count: number;
  summary: string;
  summary_char_count: number;
  agent_id: number | null;
  group_id: number | null;
  model_id: string;
  created_at: string;
  updated_at: string;
}
