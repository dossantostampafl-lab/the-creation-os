import { createHash } from 'node:crypto';
import { expect, test } from '@playwright/test';
const bytes = Buffer.from('verified-apk-bytes');
const file = {id:'android-debug',title:'Android Debug',filename:'creation-debug.apk',type:'apk',variant:'debug',size_bytes:bytes.length,sha256:createHash('sha256').update(bytes).digest('hex')};
async function showPanel(page: import('@playwright/test').Page) {
  await page.addInitScript(() => localStorage.setItem('creation_access_token','builds-test-token'));
  await page.goto('/');
  await page.evaluate(async () => {
    const [react,reactDom,{BuildsPanel}] = await Promise.all([
      import('/node_modules/.vite/deps/react.js'), import('/node_modules/.vite/deps/react-dom_client.js'), import('/src/BuildsPanel.tsx'),
    ]);
    document.getElementById('root')!.style.display='none';
    const node=document.createElement('div'); document.body.append(node);
    reactDom.default.createRoot(node).render(react.default.createElement(BuildsPanel));
  });
}
test('verified files download through Creator authentication', async ({page}) => {
  await page.route('**/api/v1/builds',route=>route.fulfill({json:{status:'available',version:'v1',files:[file]}}));
  await page.route('**/api/v1/builds/android-debug/download',route=>{
    expect(route.request().headers().authorization).toBe('Bearer builds-test-token');
    return route.fulfill({body:bytes,contentType:'application/octet-stream'});
  });
  await showPanel(page);
  const panel=page.getByRole('region',{name:'Downloads Android'}).last();
  await expect(panel.getByText('Debug para testes; não é uma versão de produção.')).toBeVisible();
  const download=page.waitForEvent('download');
  await panel.getByRole('button',{name:'Baixar Android Debug'}).click();
  expect((await download).suggestedFilename()).toBe('creation-debug.apk');
  await expect(panel.getByRole('status')).toContainText('SHA-256');
});
test('missing builds have no download button and failed list can retry',async({page})=>{
  let failed=true;
  await page.route('**/api/v1/builds',route=>failed?route.fulfill({status:503,json:{detail:'invalid artifact'}}):route.fulfill({json:{status:'not_configured',version:null,files:[]}}));
  await showPanel(page);
  const panel=page.getByRole('region',{name:'Downloads Android'}).last();
  await expect(panel.getByRole('alert')).toContainText('Não foi possível verificar');
  failed=false;
  await panel.getByRole('button',{name:'Atualizar arquivos'}).click();
  await expect(panel.getByText(/Nenhum arquivo publicado/)).toBeVisible();
  await expect(panel.getByRole('button',{name:/^Baixar/})).toHaveCount(0);
});
test('corrupt download is blocked and can retry',async({page})=>{
  let corrupt=true; let downloads=0;
  page.on('download',()=>downloads++);
  await page.route('**/api/v1/builds',route=>route.fulfill({json:{status:'available',version:'v1',files:[file]}}));
  await page.route('**/api/v1/builds/android-debug/download',route=>route.fulfill({body:corrupt?Buffer.from('corrupt'):bytes}));
  await showPanel(page);
  const panel=page.getByRole('region',{name:'Downloads Android'}).last();
  await panel.getByRole('button',{name:'Baixar Android Debug'}).click();
  await expect(panel.getByRole('alert')).toContainText('verificação de integridade');
  expect(downloads).toBe(0); corrupt=false;
  const download=page.waitForEvent('download');
  await panel.getByRole('button',{name:'Baixar Android Debug'}).click();
  expect((await download).suggestedFilename()).toBe('creation-debug.apk');
});
