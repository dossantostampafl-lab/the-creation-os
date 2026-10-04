import { expect, test, type Page } from '@playwright/test';
const mission = { id: 'mission-1', inception_id: 'inception-1', title: 'Preparar relatório', objective: 'Revisar evidências', status: 'drafted' };
async function mount(page: Page, failPlan = false, committedPlanResponseLost = false, inceptionResponseLost = false) {
  const calls: {path: string; body: any}[] = [];
  let status = 'drafted'; let planFails = failPlan;
  await page.addInitScript(() => { localStorage.setItem('creation_access_token', 'test-token'); localStorage.setItem('creation_conversation_id', 'conversation-1'); });
  await page.route('**/api/v1/**', async route => {
    const request = route.request(); const path = new URL(request.url()).pathname.replace('/api/v1', '');
    const body = request.postDataJSON();
    if (request.method() !== 'GET') calls.push({path, body});
    const respond = (value: unknown, code = 200) => route.fulfill({status:code,contentType:'application/json',body:JSON.stringify(value)});
    if (path === '/universes') return respond([{id:'universe-1',code:'engineering',name:'Engineering',active:true}]);
    if (path === '/missions' && request.method() === 'GET') return respond(calls.some(c => c.path === '/missions') ? [{...mission,status}] : []);
    if (path === '/conversations/conversation-1/messages') return respond({id:'source-1'});
    if (path === '/inceptions' && request.method() === 'GET') return respond([
      {id:'other-inception',conversation_id:'conversation-1',source_message_id:'other-source',status:'proposed'},
      ...(calls.some(c=>c.path==='/inceptions') ? [{id:'inception-1',conversation_id:'conversation-1',source_message_id:'source-1',status:'proposed'}] : []),
    ]);
    if (path === '/inceptions') {
      if (inceptionResponseLost) { inceptionResponseLost = false; return route.abort('failed'); }
      if (calls.filter(c=>c.path==='/inceptions').length>1) return respond({detail:'Duplicate inception source'},409);
      return respond({id:'inception-1',status:'proposed'});
    }
    if (path === '/inceptions/inception-1') return respond({id:'inception-1',status:calls.some(c=>c.path.endsWith('/approve'))?'approved':calls.some(c=>c.path.endsWith('/submit'))?'awaiting_creator_decision':'proposed'});
    if (path.includes('/inceptions/inception-1/')) return respond({id:'inception-1',status:path.endsWith('submit')?'awaiting_creator_decision':'approved'});
    if (path === '/missions') return respond(mission);
    if (path.endsWith('/plan')) { if (committedPlanResponseLost) { committedPlanResponseLost = false; status = 'planned'; return route.abort('failed'); } if (planFails) { planFails = false; return respond({detail:'Unavailable'},503); } status = 'planned'; return respond({...mission,status}); }
    if (path.endsWith('/validate')) { status = 'validated'; return respond({...mission,status}); }
    if (path.endsWith('/start')) { status = 'executing'; return respond({...mission,status}); }
    if (path.endsWith('/tasks')) return respond([{id:'task-1',mission_id:'mission-1',status:'failed',attempt_count:1,max_attempts:3,error_json:{message:'Provider unavailable'}}]);
    if (path === '/missions/mission-1') return respond({...mission,status});
    return respond([]);
  });
  await page.route('http://127.0.0.1:4173/', route => route.fulfill({contentType:'text/html',body:'<html><body></body></html>'}));
  await page.goto('/');
  await renderWorkbench(page);
  return calls;
}
async function renderWorkbench(page: Page) {
  await page.evaluate(async () => {
    const root = document.createElement('div'); root.id = 'mission-test'; document.body.replaceChildren(root);
    try {
      const React = await import('/node_modules/.vite/deps/react.js');
      const ReactDOM = await import('/node_modules/.vite/deps/react-dom_client.js');
      const { createRoot } = ReactDOM.default;
      const RefreshRuntime = await import('/@react-refresh');
      RefreshRuntime.default.injectIntoGlobalHook(window);
      Object.assign(window, {$RefreshReg$:()=>{}, $RefreshSig$:()=> (type:unknown)=>type});
      const { MissionWorkbench } = await import('/src/MissionWorkbench.tsx');
      createRoot(root).render(React.default.createElement(MissionWorkbench,{onChanged:()=>{}}));
    } catch (error) { root.textContent = String(error); }
  });
  await expect(page.getByRole('heading',{name:'Criar e planejar missão'})).toBeVisible();
}
async function fillPlan(page: Page) {
  await page.getByLabel('Título da missão').fill('Preparar relatório');
  await page.getByLabel('Objetivo da missão').fill('Revisar evidências');
  await page.getByLabel('Estratégia').fill('Coletar e revisar');
  await page.getByLabel('Título da etapa 1').fill('Coletar');
  await page.getByLabel('Descrição da etapa 1').fill('Coletar evidências');
  await page.getByLabel('Universe da etapa 1').selectOption('engineering');
  await page.getByRole('button',{name:'Adicionar etapa'}).click();
  await page.getByLabel('Título da etapa 2').fill('Revisar');
  await page.getByLabel('Descrição da etapa 2').fill('Revisar evidências');
  await page.getByLabel('Universe da etapa 2').selectOption('engineering');
}
test('creates and validates a manual plan with a Creator source and explicit start', async ({page}) => {
  const calls = await mount(page); await fillPlan(page);
  await page.getByRole('button',{name:'Revisar criação e plano'}).click(); expect(calls).toEqual([]);
  await page.getByRole('button',{name:'Confirmar criação e validação'}).click();
  await expect(page.getByText('Missão validada. Aguardando sua autorização.')).toBeVisible();
  const plan = calls.find(c => c.path.endsWith('/plan'))!.body;
  expect(plan.steps[1]).toMatchObject({position:2,depends_on:['step_1'],universe:'engineering'});
  expect(calls.map(c=>c.path)).toEqual(['/conversations/conversation-1/messages','/inceptions','/inceptions/inception-1/submit','/inceptions/inception-1/approve','/missions','/missions/mission-1/plan','/missions/mission-1/validate']);
  await page.getByRole('button',{name:'Autorizar e iniciar'}).click(); expect(calls.some(c=>c.path.endsWith('/start'))).toBeFalsy();
  await page.getByRole('button',{name:'Confirmar início'}).click(); await expect(page.getByText('executing',{exact:true})).toBeVisible();
  expect(calls.filter(c=>c.path.endsWith('/start'))).toHaveLength(1);
});
test('restores a partially saved plan after reload without duplicating mission or inception', async ({page}) => {
  const calls = await mount(page,true); await fillPlan(page);
  await page.getByRole('button',{name:'Revisar criação e plano'}).click();
  await page.getByRole('button',{name:'Confirmar criação e validação'}).click();
  await expect(page.getByRole('alert')).toContainText('Progresso salvo');
  await page.reload(); await renderWorkbench(page);
  await expect(page.getByLabel('Título da missão')).toHaveValue('Preparar relatório');
  await page.getByRole('button',{name:'Continuar criação e plano'}).click();
  await page.getByRole('button',{name:'Confirmar criação e validação'}).click();
  await expect(page.getByText('Missão validada. Aguardando sua autorização.')).toBeVisible();
  expect(calls.filter(c=>c.path === '/missions')).toHaveLength(1);
  expect(calls.filter(c=>c.path === '/inceptions')).toHaveLength(1);
  expect(calls.filter(c=>c.path.endsWith('/plan'))).toHaveLength(2);
});
test('shows authoritative mission tasks and their failure details', async ({page}) => {
  await mount(page); await fillPlan(page);
  await page.getByRole('button',{name:'Revisar criação e plano'}).click();
  await page.getByRole('button',{name:'Confirmar criação e validação'}).click();
  await page.getByRole('button',{name:'Acompanhar missão'}).click();
  await expect(page.getByText('Provider unavailable')).toBeVisible(); await expect(page.getByText('Tentativa 1 de 3')).toBeVisible();
});


test('keeps the submitted plan immutable when commit succeeds but the response is lost', async ({page}) => {
  const calls = await mount(page,false,true); await fillPlan(page);
  await page.getByRole('button',{name:'Revisar criação e plano'}).click();
  await page.getByRole('button',{name:'Confirmar criação e validação'}).click();
  await expect(page.getByRole('alert')).toContainText('Progresso salvo');
  await expect(page.getByLabel('Estratégia')).not.toBeEditable();
  await expect(page.getByLabel('Descrição da etapa 2')).not.toBeEditable();
  await expect(page.getByRole('button',{name:'Adicionar etapa'})).toBeDisabled();
  await page.reload(); await renderWorkbench(page);
  await expect(page.getByLabel('Estratégia')).not.toBeEditable();
  await expect(page.getByLabel('Estratégia')).toHaveValue('Coletar e revisar');
  await page.getByRole('button',{name:'Continuar criação e plano'}).click();
  await page.getByRole('button',{name:'Confirmar criação e validação'}).click();
  await expect(page.getByText('Missão validada. Aguardando sua autorização.')).toBeVisible();
  expect(calls.filter(c=>c.path.endsWith('/plan'))).toHaveLength(1);
  expect(calls.filter(c=>c.path.endsWith('/validate'))).toHaveLength(1);
  expect(calls.find(c=>c.path.endsWith('/plan'))!.body.strategy).toBe('Coletar e revisar');
});


test('recovers a committed inception by its conversation and source after a lost response', async ({page}) => {
  const calls = await mount(page,false,false,true); await fillPlan(page);
  await page.getByRole('button',{name:'Revisar criação e plano'}).click();
  await page.getByRole('button',{name:'Confirmar criação e validação'}).click();
  await expect(page.getByRole('alert')).toContainText('Progresso salvo');
  await page.reload(); await renderWorkbench(page);
  await page.getByRole('button',{name:'Continuar criação e plano'}).click();
  await page.getByRole('button',{name:'Confirmar criação e validação'}).click();
  await expect(page.getByText('Missão validada. Aguardando sua autorização.')).toBeVisible();
  expect(calls.filter(c=>c.path==='/inceptions')).toHaveLength(1);
  expect(calls.filter(c=>c.path.endsWith('/messages'))).toHaveLength(1);
  expect(calls.some(c=>c.path.includes('other-inception'))).toBeFalsy();
});
