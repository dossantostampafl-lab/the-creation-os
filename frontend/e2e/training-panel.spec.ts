import { expect, test } from '@playwright/test';
const agent = {id:'agent-one',code:'stf-red-recon',name:'STF Red Recon',cell:'red',specialty:'reconnaissance',active:true,registered:true};
async function show(page: import('@playwright/test').Page) {
  await page.addInitScript(()=>localStorage.setItem('creation_access_token','training-token'));
  await page.goto('/');
  await page.evaluate(async()=>{
    const [react,dom,{TrainingPanel}] = await Promise.all([import('/node_modules/.vite/deps/react.js'),import('/node_modules/.vite/deps/react-dom_client.js'),import('/src/TrainingPanel.tsx')]);
    document.getElementById('root')!.style.display='none';const node=document.createElement('div');document.body.append(node);dom.default.createRoot(node).render(react.default.createElement(TrainingPanel));
  });
}
test('pause and resume use real agent API and prevent paused training',async({page})=>{
  let active=true; let calls=0;
  await page.route('**/api/v1/cyber-range/training',route=>route.fulfill({json:{worker_enabled:true,controller_configured:true,environment:'cyber_range:lab-a',agents:[{...agent,active}],runs:[]}}));
  await page.route('**/api/v1/agents/agent-one/*',route=>{
    expect(route.request().headers().authorization).toBe('Bearer training-token');active=route.request().url().endsWith('/activate');calls++;return route.fulfill({json:{}});
  });
  await show(page);const panel=page.getByRole('region',{name:'Treinamento Cyber Range'}).last();
  await panel.getByRole('button',{name:'Pausar STF Red Recon'}).click();
  await expect(panel.getByRole('button',{name:'Treinar STF Red Recon'})).toBeDisabled();
  await panel.getByRole('button',{name:'Retomar STF Red Recon'}).click();
  await expect(panel.getByRole('button',{name:'Treinar STF Red Recon'})).toBeEnabled();expect(calls).toBe(2);
});
test('request queues fixed campaign and displays actual queued run',async({page})=>{
  let queued=false;
  await page.route('**/api/v1/cyber-range/training',route=>route.fulfill({json:{worker_enabled:true,controller_configured:true,environment:'cyber_range:lab-a',agents:[agent],runs:queued?[{id:'run-one',mission_id:'stf-training:stf-red-recon',state:'QUEUED',desired_state:'RUN',created_at:new Date().toISOString()}]:[]}}));
  await page.route('**/api/v1/cyber-range/training/start',route=>{expect(route.request().postDataJSON()).toEqual({agent_code:'stf-red-recon'});queued=true;return route.fulfill({json:{status:'queued',run_id:'run-one'}});});
  await show(page);const panel=page.getByRole('region',{name:'Treinamento Cyber Range'}).last();
  await panel.getByRole('button',{name:'Treinar STF Red Recon'}).click();
  await expect(panel.getByText('Ciclo run-one: QUEUED')).toBeVisible();await expect(panel.getByRole('button',{name:'Treinar STF Red Recon'})).toBeDisabled();
});
test('unavailable roster has a recovery control',async({page})=>{
  let failed=true;
  await page.route('**/api/v1/cyber-range/training',route=>failed?route.fulfill({status:503}):route.fulfill({json:{worker_enabled:false,controller_configured:false,environment:'cyber_range:lab-a',agents:[agent],runs:[]}}));
  await show(page);const panel=page.getByRole('region',{name:'Treinamento Cyber Range'}).last();
  await expect(panel.getByRole('alert')).toBeVisible();failed=false;await panel.getByRole('button',{name:'Atualizar treinamento'}).click();
  await expect(panel.getByRole('alert')).toHaveCount(0);await expect(panel.getByRole('button',{name:'Treinar STF Red Recon'})).toBeDisabled();
});
