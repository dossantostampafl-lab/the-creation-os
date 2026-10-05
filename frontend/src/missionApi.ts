import { api } from './api';
import type { ConversationMessage, Inception, Mission } from './api';
import type { AgentView, UniverseView } from './types';

export type ManualMissionPlan = {
  strategy: string;
  steps: { step_key: string; title: string; description: string; universe: string; position: number; depends_on: string[]; completion_criteria: Record<string, unknown> }[];
  completion_criteria: Record<string, unknown>;
};
export type MissionTask = {
  id: string; mission_id: string; status: string; attempt_count: number; max_attempts: number;
  error_json: Record<string, unknown>; output_json?: Record<string, unknown>;
};
export const fetchMissionAgents = () => api<AgentView[]>('/agents');
export const fetchMissionUniverses = () => api<UniverseView[]>('/universes');
export const fetchAllMissions = () => api<Mission[]>('/missions');
export const fetchMissionTasks = (id: string) => api<MissionTask[]>(`/missions/${id}/tasks`);
/** Keep the origin meaningful within MessageRequest's character and serialized UTF-8 bounds. */
export function missionSourceContent(title: string, objective: string): string {
  const characters = Array.from(`${title}\n${objective}`);
  const encoder = new TextEncoder();
  const excerpt = (length: number) => characters.slice(0,length).join('') + (length < characters.length ? '…' : '');
  let low = 0;
  let high = Math.min(characters.length,3900);
  while (low < high) {
    const middle = Math.ceil((low + high) / 2);
    if (encoder.encode(JSON.stringify(excerpt(middle))).byteLength <= 8000) low = middle;
    else high = middle - 1;
  }
  return excerpt(low);
}

export const createMissionSource = (conversationId: string, content: string, clientMessageId: string) =>
  api<ConversationMessage>(`/conversations/${conversationId}/messages`, {method:'POST',body:JSON.stringify({content,client_message_id:clientMessageId,metadata:{}})});
export const createManualInception = (conversationId: string, sourceId: string, title: string, objective: string) =>
  api<Inception>('/inceptions', {method:'POST',body:JSON.stringify({conversation_id:conversationId,source_message_id:sourceId,title,description:objective})});
export const submitManualInception = (id: string) => api<Inception>(`/inceptions/${id}/submit`, {method:'POST'});
export const createManualMission = (inceptionId: string, title: string, objective: string) =>
  api<Mission>('/missions', {method:'POST',body:JSON.stringify({inception_id:inceptionId,title,objective})});
export const saveManualMissionPlan = (id: string, plan: ManualMissionPlan) =>
  api<Mission>(`/missions/${id}/plan`, {method:'POST',body:JSON.stringify(plan)});
export const validateManualMission = (id: string) => api<Mission>(`/missions/${id}/validate`, {method:'POST'});
