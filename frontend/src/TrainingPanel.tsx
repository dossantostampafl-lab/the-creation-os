import { useEffect, useState } from 'react';
import { fetchTraining, requestTraining, setTrainingAgentActive } from './trainingApi';
import type { TrainingState } from './trainingApi';

export function TrainingPanel() {
  const [state,setState] = useState<TrainingState|null>(null);
  const [busy,setBusy] = useState(false);
  const [error,setError] = useState('');
  const [message,setMessage] = useState('');
  async function refresh() { setState(await fetchTraining()); }
  async function run(action:()=>Promise<void>) {
    setBusy(true);setError('');setMessage('');
    try { await action(); }
    catch { setError('Não foi possível concluir a ação. Atualize o treinamento para conferir o estado real e tente novamente.'); }
    finally { setBusy(false); }
  }
  useEffect(()=>{let disposed=false;void fetchTraining().then(value=>{if(!disposed)setState(value);}).catch(()=>{if(!disposed)setError('Treinamento indisponível. Atualize para tentar novamente.');});return()=>{disposed=true;};},[]);
  const activeRun = state?.active_run ?? state?.runs.find(run=>!['COMPLETED','ABORTED'].includes(run.state));
  const rangeBusy = state?.range_busy ?? !!activeRun;
  return <section aria-label="Treinamento Cyber Range">
    <h3>Agentes do Cyber Range</h3>
    <p>Treinamento na campanha privada do laboratório. Pausar um agente impede novos ciclos; o ciclo em execução continua.</p>
    <button disabled={busy} onClick={()=>void run(refresh)}>Atualizar treinamento</button>
    {state && <>
      <p>Worker: {state.worker_enabled?'habilitado':'desabilitado'} · laboratório: {state.controller_configured?'configurado':'não configurado'}</p>
      {activeRun && <p role="status">Ciclo {activeRun.id}: {activeRun.state}{activeRun.desired_state==='CANCEL'?' · cancelamento solicitado':''}</p>}
      {rangeBusy && !activeRun && <p role="status">O laboratório possui um ciclo em andamento. Aguarde sua conclusão.</p>}
      {state.agents.map(agent=><article className="decision" key={agent.code}>
        <div><strong>{agent.name}</strong><small>{agent.cell} · {agent.specialty}</small><p>{!agent.registered?'Aguardando registro pelo worker':agent.active?'Ativo':'Pausado'}</p></div>
        <div><button disabled={busy||!agent.id} onClick={()=>void run(async()=>{await setTrainingAgentActive(agent.id!,!agent.active);await refresh();})}>{agent.active?'Pausar':'Retomar'} {agent.name}</button>
        <button disabled={busy||!agent.active||!state.worker_enabled||!state.controller_configured||rangeBusy} onClick={()=>void run(async()=>{const result=await requestTraining(agent.code);setMessage(result.status==='queued'?'Ciclo enfileirado; aguarde a execução pelo worker.':'O laboratório já possui um ciclo em andamento.');await refresh();})}>Treinar {agent.name}</button></div>
      </article>)}
      <h4>Ciclos recentes</h4>
      {state.runs.length?<ul>{state.runs.map(run=><li key={run.id}>{run.mission_id} · {run.state} · {new Date(run.created_at).toLocaleString()}</li>)}</ul>:<p>Nenhum ciclo registrado.</p>}
    </>}
    {error && <p role="alert">{error}</p>}
    <p role="status" aria-live="polite">{message}</p>
  </section>;
}
