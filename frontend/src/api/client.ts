import axios from 'axios';
import type { Agent, Group, Task, TaskStatus } from '../types';

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
};
