import { useCallback, useEffect, useRef, useState } from 'react';
import { CREATOR_CONVERSATION_KEY, createConversation, decideInception, fetchInception, fetchInceptions, fetchMission, startMission } from './api';
import type { Mission } from './api';
import { newRequestId } from './requestId';
import { createManualInception, createManualMission, createMissionSource, missionSourceContent, fetchAllMissions, fetchMissionTasks, fetchMissionUniverses, fetchMissionAgents, saveManualMissionPlan, submitManualInception, validateManualMission } from './missionApi';
import type { MissionTask } from './missionApi';
import type { AgentView, UniverseView } from './types';
import './MissionWorkbench.css';

type Step = {title:string;description:string;universe:string};
type Draft = {
  title:string;objective:string;strategy:string;steps:Step[];
  conversationId?:string;sourceId?:string;sourceRequestId?:string;inceptionId?:string;missionId?:string;planSaved?:boolean;planSubmitted?:boolean;
};
const DRAFT_KEY = 'creation_manual_mission_draft';
const emptyDraft = (): Draft => ({title:'',objective:'',strategy:'',steps:[{title:'',description:'',universe:''}]});
function loadDraft(): Draft {
  try {
    const value = JSON.parse(sessionStorage.getItem(DRAFT_KEY) ?? 'null');
    if (value && typeof value.title === 'string' && typeof value.objective === 'string' && typeof value.strategy === 'string' && Array.isArray(value.steps) && value.steps.length && value.steps.every((step:Step) => typeof step.title === 'string' && typeof step.description === 'string' && typeof step.universe === 'string')) return value as Draft;
  } catch { /* A malformed or unavailable local draft must not block the form. */ }
  return emptyDraft();
}
function readableError(error: unknown): string {
  const message = error instanceof Error ? error.message : '';
  if (message === 'AUTH_REQUIRED') return 'Sessão expirada. Entre novamente.';
  if (message === 'HTTP_400' || message === 'HTTP_409' || message === 'HTTP_422') return 'A ação não está disponível no estado atual. Atualize a missão e revise os dados.';
  return 'Serviço indisponível. Tente novamente.';
}
export function MissionWorkbench({onChanged}: {onChanged:()=>void}) {
  const [draft,setDraft] = useState<Draft>(loadDraft);
  const draftRef = useRef(draft);
  const [universes,setUniverses] = useState<UniverseView[]>([]);
  const [agents,setAgents] = useState<AgentView[]>([]);
  const [missions,setMissions] = useState<Mission[]>([]);
  const [selected,setSelected] = useState<Mission|null>(null);
  const [tasks,setTasks] = useState<MissionTask[]|null>(null);
  const [busy,setBusy] = useState(false);
  const [loading,setLoading] = useState(false);
  const [error,setError] = useState('');
  const [notice,setNotice] = useState('');
  const [confirm,setConfirm] = useState<'create'|'start'|'validate'|null>(null);
  const [startId,setStartId] = useState<string|null>(null);
  function save(value: Draft) {
    draftRef.current = value; setDraft(value);
    sessionStorage.setItem(DRAFT_KEY,JSON.stringify(value));
  }
  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const [all,available,executors] = await Promise.all([fetchAllMissions(),fetchMissionUniverses(),fetchMissionAgents()]);
      setMissions(all); setUniverses(available); setAgents(executors); setError('');
    } catch (failure) { setError(`Não foi possível carregar missões e Universes. ${readableError(failure)}`); }
    finally { setLoading(false); }
  },[]);
  useEffect(() => { void refresh(); },[refresh]);
  function change(field:'title'|'objective'|'strategy',value:string) { save({...draftRef.current,[field]:value}); setConfirm(null); }
  function changeStep(index:number,field:keyof Step,value:string) {
    save({...draftRef.current,steps:draftRef.current.steps.map((step,i) => i === index ? {...step,[field]:value} : step)}); setConfirm(null);
  }
  async function track(id:string) {
    setBusy(true); setError(''); setTasks(null);
    try { const [mission,items] = await Promise.all([fetchMission(id),fetchMissionTasks(id)]); setSelected(mission); setTasks(items); }
    catch (failure) { setError(`Não foi possível atualizar a missão. ${readableError(failure)}`); }
    finally { setBusy(false); }
  }
  async function createAndPlan() {
    if (busy) return;
    setBusy(true); setError(''); setNotice('');
    let current = draftRef.current;
    const remember = (patch: Partial<Draft>) => { current = {...current,...patch}; save(current); };
    try {
      if (!current.conversationId) {
        const existing = localStorage.getItem(CREATOR_CONVERSATION_KEY);
        const id = existing ?? (await createConversation('Planejamento de missão')).id;
        localStorage.setItem(CREATOR_CONVERSATION_KEY,id); remember({conversationId:id});
      }
      if (!current.sourceId) {
        if (!current.sourceRequestId) remember({sourceRequestId:newRequestId()});
        remember({sourceId:(await createMissionSource(current.conversationId!,missionSourceContent(current.title,current.objective),current.sourceRequestId!)).id});
      }
      if (!current.inceptionId) {
        // The Conversation/source pair is unique; recover a committed creation before retrying POST.
        const existing = (await fetchInceptions()).find(item => item.conversation_id === current.conversationId && item.source_message_id === current.sourceId);
        remember({inceptionId:existing?.id ?? (await createManualInception(current.conversationId!,current.sourceId!,current.title,current.objective)).id});
      }
      let inception = await fetchInception(current.inceptionId!);
      if (inception.status === 'proposed') inception = await submitManualInception(inception.id);
      if (inception.status === 'awaiting_creator_decision') inception = await decideInception(inception.id,'approve');
      if (inception.status !== 'approved') throw new Error('HTTP_409');
      if (!current.missionId) {
        // Recover a Mission if creation succeeded but the browser lost its response.
        const existing = (await fetchAllMissions()).find(item => item.inception_id === current.inceptionId);
        remember({missionId:existing?.id ?? (await createManualMission(current.inceptionId!,current.title,current.objective)).id});
      }
      let mission = await fetchMission(current.missionId!);
      if (mission.status === 'drafted') {
        // Persist the submitted version before POST: a lost response may hide a committed plan.
        remember({planSubmitted:true});
        mission = await saveManualMissionPlan(mission.id,{
        strategy:current.strategy,
        completion_criteria:{},
        steps:current.steps.map((step,index) => ({...step,step_key:`step_${index+1}`,position:index+1,depends_on:index ? [`step_${index}`] : [],completion_criteria:{}})),
      });
      }
      if (mission.status === 'planned') { remember({planSaved:true,planSubmitted:false}); mission = await validateManualMission(mission.id); }
      if (mission.status !== 'validated') throw new Error('HTTP_409');
      setSelected(mission); setTasks(null); setConfirm(null); setNotice('Missão validada. Aguardando sua autorização.');
      setMissions(await fetchAllMissions()); onChanged();
    } catch (failure) {
      if (!current.sourceId && failure instanceof Error && failure.message === 'HTTP_422') {
        // A rejected request created no message; allow correcting the source with a new key.
        remember({sourceRequestId:undefined});
      }
      if (current.missionId && current.planSubmitted) {
        try {
          const persisted = await fetchMission(current.missionId);
          remember(persisted.status === 'drafted' ? {planSubmitted:false,planSaved:false} : {planSubmitted:false,planSaved:true});
        } catch { /* Preserve the submitted version while the server state is uncertain. */ }
      }
      setError(`${readableError(failure)} Progresso salvo; continue a partir da última etapa concluída.`); setConfirm(null); onChanged();
    }
    finally { setBusy(false); }
  }
  async function execute() {
    if (busy || !startId) return;
    setBusy(true); setError('');
    try {
      const mission = confirm === 'validate' ? await validateManualMission(startId) : await startMission(startId);
      setSelected(mission); setTasks(null); setConfirm(null); setNotice(confirm === 'validate' ? 'Missão validada. Aguardando sua autorização.' : 'Início da missão confirmado.');
      setMissions(await fetchAllMissions()); onChanged();
    } catch (failure) { setError(readableError(failure)); setConfirm(null); onChanged(); }
    finally { setBusy(false); }
  }
  const locked = Boolean(draft.sourceId || draft.sourceRequestId);
  const hasExecutor = (universe:UniverseView) => agents.some(agent=>agent.active && agent.universe_id===universe.id);
  const unavailable = universes.filter(universe=>!universe.active || !hasExecutor(universe));
  const selectedUnavailable = draft.steps.some(step=>step.universe && !universes.some(universe=>universe.code===step.universe && universe.active && hasExecutor(universe)));
  const completed = Boolean(selected && draft.missionId && selected.id === draft.missionId && !['drafted','planned'].includes(selected.status));
  return <section className="mission-workbench" aria-label="Planejamento e acompanhamento de missões">
    <h3>Criar e planejar missão</h3>
    <p>Defina um plano manual. Ao confirmar, a proposta será aprovada e a missão validada. As etapas serão executadas em sequência.</p>
    <form onSubmit={event => {event.preventDefault();setConfirm('create');setError('');}}>
      <fieldset disabled={busy}>
        <label>Título da missão<input disabled={locked} value={draft.title} minLength={3} maxLength={256} required onChange={event=>change('title',event.target.value)}/></label>
        <label>Objetivo da missão<textarea disabled={locked} value={draft.objective} maxLength={8000} required onChange={event=>change('objective',event.target.value)}/></label>
        <label>Estratégia<textarea disabled={draft.planSaved || draft.planSubmitted} value={draft.strategy} maxLength={12000} required onChange={event=>change('strategy',event.target.value)}/></label>
        {draft.steps.map((step,index) => <fieldset disabled={draft.planSaved || draft.planSubmitted} key={index} className="mission-step"><legend>Etapa {index+1}</legend>
          <label>Título da etapa {index+1}<input value={step.title} maxLength={256} required onChange={event=>changeStep(index,'title',event.target.value)}/></label>
          <label>Descrição da etapa {index+1}<textarea value={step.description} maxLength={8000} required onChange={event=>changeStep(index,'description',event.target.value)}/></label>
          <label>Universe da etapa {index+1}<select value={step.universe} required onChange={event=>changeStep(index,'universe',event.target.value)}><option value="">Selecione um Universe</option>{universes.map(item=><option key={item.id} value={item.code} disabled={!item.active || !hasExecutor(item)}>{item.name}{!item.active?' (inativo)':hasExecutor(item)?'':' (sem agente ativo)'}</option>)}</select></label>
          {index>0 && <small>Depende da etapa {index}.</small>}
          {draft.steps.length>1 && <button type="button" onClick={()=>save({...draftRef.current,steps:draftRef.current.steps.filter((_,i)=>i!==index)})}>Remover etapa {index+1}</button>}
        </fieldset>)}
        <button type="button" disabled={draft.planSaved || draft.planSubmitted} onClick={()=>save({...draftRef.current,steps:[...draftRef.current.steps,{title:'',description:'',universe:''}]})}>Adicionar etapa</button>
      </fieldset>
      {!completed && <button type="submit" disabled={busy || loading || !universes.length || selectedUnavailable}>{locked?'Continuar criação e plano':'Revisar criação e plano'}</button>}
    </form>
    {confirm === 'create' && <div className="decision-confirm"><p>Confirmar aprovação da proposta e salvar o plano de “{draft.title}” com {draft.steps.length} etapa(s)?</p><button type="button" disabled={busy || selectedUnavailable} onClick={()=>void createAndPlan()}>Confirmar criação e validação</button><button type="button" disabled={busy} onClick={()=>setConfirm(null)}>Voltar ao plano</button></div>}
    {notice && <p role="status">{notice}</p>}
    {busy && <p role="status">Salvando ou atualizando missão…</p>}
    {error && <p className="console-error" role="alert">{error}</p>}
    {locked && <p>Os dados estão preservados para continuar esta missão.</p>}
    {completed && <button type="button" disabled={busy} onClick={()=>{save(emptyDraft());setNotice('');}}>Planejar outra missão</button>}
    {unavailable.map(universe=><p key={universe.id}>{universe.name}: {universe.active?'sem agente ativo.':'Universe inativo.'}</p>)}
    <h3>Acompanhar missões</h3>
    <button type="button" disabled={busy || loading} onClick={()=>void refresh()}>Atualizar missões e Universes</button>
    {loading && <p role="status">Carregando missões…</p>}
    {!loading && !missions.length && <p>Nenhuma missão disponível.</p>}
    <div className="stack">{missions.map(mission=><article className="decision" key={mission.id}>
      <div><strong>{mission.title}</strong><small>{mission.objective}</small><span className="pill">{mission.status}</span></div>
      <div className="decision-actions"><button type="button" disabled={busy} onClick={()=>void track(mission.id)}>Acompanhar missão</button>
        {['validated','authorized','distributed'].includes(mission.status) && <button type="button" disabled={busy} onClick={()=>{setStartId(mission.id);setConfirm('start');}}>Autorizar e iniciar</button>}
        {mission.status==='planned' && <button type="button" disabled={busy} onClick={()=>{setStartId(mission.id);setConfirm('validate');}}>Validar plano salvo</button>}
      </div>
      {startId===mission.id && (confirm==='start' || confirm==='validate') && <div className="decision-confirm"><p>{confirm==='start'?'Autorizar, distribuir e iniciar esta missão?':'Validar o plano desta missão?'}</p><button type="button" disabled={busy} onClick={()=>void execute()}>{confirm==='start'?'Confirmar início':'Confirmar validação'}</button><button type="button" disabled={busy} onClick={()=>setConfirm(null)}>Voltar</button></div>}
    </article>)}</div>
    {selected && tasks!==null && <div aria-label="Tarefas da missão"><h4>Tarefas de {selected.title}</h4>{!tasks.length && <p>Nenhuma tarefa distribuída.</p>}{tasks.map(task=><article className="decision" key={task.id}><strong>{task.status}</strong><small>Tentativa {task.attempt_count} de {task.max_attempts}</small>{Object.entries(task.error_json ?? {}).map(([key,value])=><p key={key}>{key}: {typeof value==='string'?value:JSON.stringify(value)}</p>)}</article>)}<button type="button" disabled={busy} onClick={()=>void track(selected.id)}>Atualizar acompanhamento</button></div>}
  </section>;
}
