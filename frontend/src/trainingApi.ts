import { api } from './api';
export type TrainingAgent = {id:string|null; code:string; name:string; cell:string; specialty:string; active:boolean; registered:boolean};
type TrainingRun = {id:string; mission_id:string; state:string; desired_state:string; created_at:string};
export type TrainingState = {active_run?:TrainingRun|null;range_busy?:boolean;worker_enabled:boolean; controller_configured:boolean; environment:string; agents:TrainingAgent[]; runs:TrainingRun[]};
export const fetchTraining = () => api<TrainingState>('/cyber-range/training');
export const requestTraining = (agent_code:string) => api<{status:string;run_id?:string}>('/cyber-range/training/start',{method:'POST',body:JSON.stringify({agent_code})});
export const setTrainingAgentActive = (id:string, active:boolean) => api(`/agents/${encodeURIComponent(id)}/${active?'activate':'deactivate'}`,{method:'POST'});
