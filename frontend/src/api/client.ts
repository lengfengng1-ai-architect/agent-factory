import axios from 'axios';
import type { Agent, Group, Task, TaskStatus, Provider, ProviderModel, ChatFile, FileSummary } from '../types';

const api = axios.create({
  baseURL: '/api',
  headers: { 'Content-Type': 'application/json' },
});

export const agentApi = {
  list: () => api.get<Agent[]>('/agents').then(r => r.data),
  get: (id: number) => api.get<Agent>(`/agents/${id}`).then(r => r.data),
  create: (data: Omit<Agent, 'id' | 'created_at'>) => api.post<Agent>('/agents', data).then(r => r.data),
  update: (id: number, data: Partial<Agent>) => api.put<Agent>(`/agents/${id}`, data).then(r => r.data),
  delete: (id: number) => api.delete(`/agents/${id}`).then(r => r.data),
};

export const groupApi = {
  list: () => api.get<Group[]>('/groups').then(r => r.data),
  get: (id: number) => api.get<Group>(`/groups/${id}`).then(r => r.data),
  create: (data: Omit<Group, 'id' | 'created_at'>) => api.post<Group>('/groups', data).then(r => r.data),
  update: (id: number, data: Partial<Group>) => api.put<Group>(`/groups/${id}`, data).then(r => r.data),
  delete: (id: number) => api.delete(`/groups/${id}`).then(r => r.data),
};

export const taskApi = {
  list: (params?: { status?: TaskStatus; assignee_type?: string; assignee_id?: number }) =>
    api.get<Task[]>('/tasks', { params }).then(r => r.data),
  get: (id: number) => api.get<Task>(`/tasks/${id}`).then(r => r.data),
  create: (data: Omit<Task, 'id' | 'created_at' | 'updated_at'>) => api.post<Task>('/tasks', data).then(r => r.data),
  update: (id: number, data: Partial<Task>) => api.put<Task>(`/tasks/${id}`, data).then(r => r.data),
  delete: (id: number) => api.delete(`/tasks/${id}`).then(r => r.data),
  execute: (id: number) => api.post(`/tasks/${id}/execute`).then(r => r.data),
  status: (id: number) => api.get<{ task_id: number; status: string; progress: number; result: string }>(`/tasks/${id}/status`).then(r => r.data),
  getConcurrency: () => api.get<{ max_concurrent_tasks: number }>('/tasks/concurrency').then(r => r.data),
  setConcurrency: (n: number) => api.put('/tasks/concurrency', { max_concurrent_tasks: n }).then(r => r.data),
};

export const providerApi = {
  list: () => api.get<Provider[]>('/providers').then(r => r.data),
  get: (id: number) => api.get<Provider>(`/providers/${id}`).then(r => r.data),
  create: (data: Omit<Provider, 'id' | 'is_builtin' | 'created_at'>) =>
    api.post<Provider>('/providers', data).then(r => r.data),
  update: (id: number, data: Partial<Provider>) =>
    api.put<Provider>(`/providers/${id}`, data).then(r => r.data),
  delete: (id: number) => api.delete(`/providers/${id}`).then(r => r.data),
  discover: (id: number, apiKey?: string) =>
    api.post(`/providers/${id}/discover`, { api_key: apiKey || '' }).then(r => r.data),
  getModels: (id: number) =>
    api.get<ProviderModel[]>(`/providers/${id}/models`).then(r => r.data),
  reset: (id: number) => api.post<Provider>(`/providers/${id}/reset`).then(r => r.data),
};

export const chatApi = {
  history: (agentId: number) =>
    api.get<{ messages: { role: string; content: string; timestamp: string }[] }>(`/agents/${agentId}/chat/history`).then(r => r.data),
};

export const groupChatApi = {
  history: (groupId: number) =>
    api.get<{ messages: { role: string; agent_id: number; agent_name: string; content: string; timestamp: string }[] }>(`/groups/${groupId}/chat/history`).then(r => r.data),
};

export const fileApi = {
  uploadAgent: (agentId: number, files: FileList) => {
    const formData = new FormData();
    for (let i = 0; i < files.length; i++) {
      formData.append('files', files[i]);
    }
    return api.post<{ files: ChatFile[] }>(`/agents/${agentId}/files/upload`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }).then(r => r.data);
  },
  uploadGroup: (groupId: number, files: FileList) => {
    const formData = new FormData();
    for (let i = 0; i < files.length; i++) {
      formData.append('files', files[i]);
    }
    return api.post<{ files: ChatFile[] }>(`/groups/${groupId}/files/upload`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }).then(r => r.data);
  },
  listAgent: (agentId: number) =>
    api.get<{ files: ChatFile[] }>(`/agents/${agentId}/files`).then(r => r.data),
  listGroup: (groupId: number) =>
    api.get<{ files: ChatFile[] }>(`/groups/${groupId}/files`).then(r => r.data),
  deleteAgent: (agentId: number, fileId: string) =>
    api.delete(`/agents/${agentId}/files/${fileId}`).then(r => r.data),
  deleteGroup: (groupId: number, fileId: string) =>
    api.delete(`/groups/${groupId}/files/${fileId}`).then(r => r.data),
};

export const summaryApi = {
  list: (params?: { agent_id?: number; group_id?: number; search?: string; limit?: number; offset?: number }) =>
    api.get<{ total: number; limit: number; offset: number; items: FileSummary[] }>('/summaries', { params }).then(r => r.data),
  get: (id: number) =>
    api.get<FileSummary>(`/summaries/${id}`).then(r => r.data),
  delete: (id: number) =>
    api.delete(`/summaries/${id}`).then(r => r.data),
};
