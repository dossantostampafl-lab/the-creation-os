import { newRequestId } from './requestId';
import { useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import { fetchDiagnostics, createKnowledgeProject, fetchKnowledgeProjects, setKnowledgeFocus, CREATOR_CONVERSATION_KEY, changeCyberRange, fetchCyberRange, revokeKnowledge, saveKnowledge, searchKnowledge } from './api';
import type { CyberRangeState, DiagnosticsSnapshot, KnowledgeEvidence } from './api';

export function ConnectedPanel() {
  const [projects, setProjects] = useState<{id:string;title:string}[]>([]);
  const [projectId, setProjectId] = useState('');
  const [projectTitle, setProjectTitle] = useState('');
  const [query, setQuery] = useState('');
  const [title, setTitle] = useState('');
  const [content, setContent] = useState('');
  const [requestId, setRequestId] = useState(() => newRequestId());
  const [evidence, setEvidence] = useState<KnowledgeEvidence[]>([]);
  const [diagnostics, setDiagnostics] = useState<DiagnosticsSnapshot | null>(null);
  const [range, setRange] = useState<CyberRangeState | null>(null);
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  async function run(action: () => Promise<void>) {
    setBusy(true); setMessage('');
    try { await action(); } catch { setMessage('Ação indisponível. Verifique sua sessão e o serviço; tente novamente.'); }
    finally { setBusy(false); }
  }
  function find(event: FormEvent) {
    event.preventDefault();
    void run(async () => {
      const result = await searchKnowledge(query, projectId || undefined);
      setEvidence(result.evidences);
      setMessage(result.status==='empty' ? 'Nenhuma evidência encontrada.' : 'Memória consultada.');
    });
  }
  function save(event: FormEvent) {
    event.preventDefault();
    void run(async () => {
      await saveKnowledge(title, content, requestId, projectId || undefined);
      setTitle(''); setContent(''); setRequestId(newRequestId());
      setMessage('Informação salva na memória de Deus.');
    });
  }
  async function refreshRange() { setRange(await fetchCyberRange()); }
  useEffect(() => {
    let disposed = false;
    const refresh = async () => {
      try {
        const snapshot = await fetchDiagnostics();
        if (!disposed) setDiagnostics(snapshot);
      } catch {
        if (!disposed) setDiagnostics(null);
      }
    };
    void refresh();
    const timer = window.setInterval(() => void refresh(), 15_000);
    return () => { disposed = true; window.clearInterval(timer); };
  }, []);
  return <section className="connected-tools" aria-label="Memória e Cyber Range">
    <h3>Memória de Deus</h3>
    <button disabled={busy} onClick={()=>void run(async()=>{setProjects(await fetchKnowledgeProjects());})}>Carregar projetos</button>
    <label>Projeto<select value={projectId} onChange={e=>setProjectId(e.target.value)}><option value="">Todos os projetos</option>{projects.map(project=><option key={project.id} value={project.id}>{project.title}</option>)}</select></label>
    <button disabled={busy} onClick={()=>void run(async()=>{const conversationId=window.localStorage.getItem(CREATOR_CONVERSATION_KEY);if(!conversationId) throw new Error('Conversation unavailable');await setKnowledgeFocus(conversationId,projectId||null);setMessage('Foco aplicado à conversa por texto e voz.');})}>Aplicar foco à conversa atual</button>
    <form onSubmit={event=>{event.preventDefault();void run(async()=>{const project=await createKnowledgeProject(projectTitle);setProjects(rows=>[...rows,project]);setProjectId(project.id);setProjectTitle('');setMessage('Projeto criado.');});}}><label>Novo projeto<input value={projectTitle} onChange={e=>setProjectTitle(e.target.value)} maxLength={200} required/></label><button disabled={busy}>Criar projeto</button></form>
    <form onSubmit={find}><label>Pesquisar evidências<input value={query} onChange={e=>setQuery(e.target.value)} required maxLength={2048}/></label><button disabled={busy}>Pesquisar</button></form>
    <form onSubmit={save}><label>Título<input value={title} onChange={e=>{setTitle(e.target.value);setRequestId(newRequestId());}} required maxLength={200}/></label><label>Informação<textarea value={content} onChange={e=>{setContent(e.target.value);setRequestId(newRequestId());}} required maxLength={262144}/></label><button disabled={busy}>Guardar na memória</button></form>
    <div className="stack">{evidence.map(item=><article className="decision" key={item.revision_id}><div><strong>{item.title}</strong><small>{item.epistemic_state}</small><p>{item.content}</p></div><button disabled={busy} onClick={()=>{if(window.confirm('Revogar esta informação e suas notas dependentes?')) void run(async()=>{await revokeKnowledge(item);setEvidence(rows=>rows.filter(row=>row.item_id!==item.item_id));setMessage('Informação revogada.');});}}>Revogar</button></article>)}</div>
    <h3>Diagnóstico do OS</h3>
    <button disabled={busy} onClick={()=>void run(async()=>{setDiagnostics(await fetchDiagnostics());})}>Atualizar diagnóstico</button>
    {diagnostics && <p>Observador: {diagnostics.observer_status} · fonte: {diagnostics.source}</p>}
    {diagnostics && (diagnostics.observations.length ? <ul>{diagnostics.observations.map(row=><li key={row.resource}>{row.resource}: {row.status} · {row.observed_at}</li>)}</ul> : <p>Sem observações recentes. Estado desconhecido; verifique o observador.</p>)}
    <h3>Cyber Range</h3>
    <button disabled={busy} onClick={()=>void run(refreshRange)}>Verificar laboratório</button>
    {range && <p>{range.message ?? 'Laboratório disponível. Cenários isolados de treinamento.'}</p>}
    {range?.status==='available' && <><div className="stack">{range.catalog?.map(scenario=><article key={scenario.id}><strong>{scenario.id}</strong><p>{scenario.description}</p><span>{range.scenarios.find(row=>row.scenario_id===scenario.id)?.status ?? 'inativo'}</span><button disabled={busy} onClick={()=>void run(async()=>{await changeCyberRange('start',scenario.id);await refreshRange();})}>Ativar cenário</button></article>)}</div><button disabled={busy} onClick={()=>void run(async()=>{await changeCyberRange('snapshots');setMessage('Snapshot criado no laboratório.');})}>Salvar snapshot</button><button disabled={busy} onClick={()=>{if(window.confirm('Limpar o estado dos cenários do laboratório?')) void run(async()=>{await changeCyberRange('reset');await refreshRange();});}}>Limpar cenários</button></>}
    <p role="status" aria-live="polite">{message}</p>
  </section>;
}
