// Manual, authenticated production QA. Only the named QA records are created.
// Never log credentials, request headers, private conversation contents or screenshots.
import { chromium, expect } from '@playwright/test';
import { createHash, randomUUID } from 'node:crypto';
import { readFile, writeFile, mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

let input = '';
for await (const chunk of process.stdin) input += chunk;
const credentials = JSON.parse(input);
input = '';
const origin = new URL(credentials.origin);
if (origin.protocol !== 'https:' || origin.username || origin.password) throw new Error('Invalid QA origin');
const root = origin.origin;
const headers = { Authorization: `Bearer ${credentials.access_token}` };
const results = [];
let stage = '';
const workspace = await mkdtemp(join(tmpdir(), 'creation-gauntlet-'));
let browser;
async function check(name, action) {
  stage = 'START';
  const started = Date.now();
  try {
    const detail = await action();
    results.push({ name, ok: true, elapsed_ms: Date.now() - started, detail });
  } catch (error) {
    // Playwright assertions can embed the whole DOM or private responses. Emit only a class.
    results.push({ name, ok: false, elapsed_ms: Date.now() - started, error: error.name,
      stage,
      ...(typeof error.code === 'string' && /^[A-Z0-9_]{1,96}$/.test(error.code) ? { code: error.code } : {}) });
  }
  console.log(JSON.stringify(results.at(-1)));
}
async function api(context, path, method = 'GET', data) {
  const response = await context.request.fetch(`${root}/api/v1${path}`, { method, headers, data, timeout: 45000 });
  if (!response.ok()) { const error = new Error('API request failed'); error.code = `HTTP_${response.status()}`; throw error; }
  return response.json();
}
async function open(context, title) {
  const conversation = await api(context, '/conversations', 'POST', { title });
  await context.addInitScript(({ token, id }) => {
    localStorage.setItem('creation_access_token', token);
    localStorage.setItem('creation_conversation_id', id);
  }, { token: credentials.access_token, id: conversation.id });
  const page = await context.newPage();
  page.setDefaultTimeout(45000);
  await page.goto(root, { waitUntil: 'domcontentloaded' });
  await expect(page.getByLabel('Message DEUS')).toBeEnabled();
  return { page, conversation };
}
async function waitForMission(context, id) {
  const deadline = Date.now() + 120000;
  while (Date.now() < deadline) {
    const state = (await api(context, `/missions/${id}`)).status;
    if (state === 'manifested') return;
    if (state === 'failed') {
      const tasks = await api(context, `/missions/${id}/tasks`);
      const error = new Error('QA mission failed'); error.name = 'MissionFailed';
      error.code = tasks.find(task => task.status === 'FAILED')?.error_json?.code;
      throw error;
    }
    await new Promise(resolve => setTimeout(resolve, 1000));
  }
  const error = new Error('QA mission timed out'); error.code = 'MISSION_TIMEOUT'; throw error;
}
function wav(pcm) {
  const header = Buffer.alloc(44);
  header.write('RIFF'); header.writeUInt32LE(36 + pcm.length, 4); header.write('WAVEfmt ', 8);
  header.writeUInt32LE(16, 16); header.writeUInt16LE(1, 20); header.writeUInt16LE(1, 22);
  header.writeUInt32LE(24000, 24); header.writeUInt32LE(48000, 28);
  header.writeUInt16LE(2, 32); header.writeUInt16LE(16, 34);
  header.write('data', 36); header.writeUInt32LE(pcm.length, 40);
  return Buffer.concat([header, pcm]);
}
try {
  browser = await chromium.launch({ args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream'] });
  const context = await browser.newContext({ permissions: ['microphone'], acceptDownloads: true });
  await check('Bounded gateway load: sixteen reads, four concurrent', async () => {
    const latencies = [];
    for (let batch = 0; batch < 4; batch++) {
      await Promise.all(Array.from({ length: 4 }, async () => {
        const started = Date.now();
        await api(context, '/health/ready');
        latencies.push(Date.now() - started);
      }));
    }
    return { requests: latencies.length, max_ms: Math.max(...latencies) };
  });
  await check('MinIO inventory', async () => ({ installed: credentials.minio_containers > 0, containers: credentials.minio_containers,
    validated: false, reason: credentials.minio_containers ? 'Endpoint still required for storage validation' : 'Absent from server inventory and repository configuration' }));
  let page;
  let conversation;
  await check('Authenticated dashboard', async () => {
    ({ page, conversation } = await open(context, `Gauntlet QA ${Date.now()}`));
    await expect(page.getByRole('button', { name: /^Vitals\b/ })).toBeVisible();
  });
  if (page) {
    await check('Typed DEUS conversation and coherent reply', async () => {
      const response = page.waitForResponse(r => r.url().endsWith(`/conversations/${conversation.id}/deus`) && r.request().method() === 'POST');
      await page.getByLabel('Message DEUS').fill('Responda apenas: quatro');
      await page.getByRole('button', { name: 'Send to DEUS' }).click();
      const reply = await response;
      if (!reply.ok()) { const error = new Error('DEUS request failed'); error.code = `DEUS_HTTP_${reply.status()}`; throw error; }
      const body = await reply.json();
      const normalized = body.response.trim().toLowerCase().replace(/[.!]/g, '');
      if (!/^(quatro|4)$/.test(normalized)) { const error = new Error('DEUS response did not match'); error.code = 'DEUS_INCOHERENT_QA_REPLY'; throw error; }
      await expect(page.locator('.deus-message').last()).toContainText(/quatro|\b4\b/i);
    });
    await check('Real UI download and SHA-256', async () => {
      await page.getByRole('button', { name: /^Vitals\b/ }).click();
      const panel = page.getByRole('region', { name: 'Downloads Android' });
      await expect(panel.getByRole('button', { name: /^Baixar / }).first()).toBeEnabled();
      const catalog = await api(context, '/builds');
      for (const file of catalog.files) {
        const event = page.waitForEvent('download');
        await panel.getByRole('button', { name: `Baixar ${file.title}`, exact: true }).click();
        const download = await event;
        const bytes = await readFile(await download.path());
        expect(bytes.length).toBe(file.size_bytes);
        expect(createHash('sha256').update(bytes).digest('hex')).toBe(file.sha256);
      }
      return { files: catalog.files.length };
    });
    await check('Training controls start and complete a fresh private campaign', async () => {
      const panel = page.getByRole('region', { name: 'Treinamento Cyber Range' });
      const refresh = panel.getByRole('button', { name: 'Atualizar treinamento' });
      const queueDeadline = Date.now() + 120000;
      let runId;
      while (Date.now() < queueDeadline && !runId) {
        stage = 'TRAINING_REFRESH';
        const refreshed = page.waitForResponse(r => r.url().endsWith('/cyber-range/training') && r.request().method() === 'GET');
        await refresh.click();
        const response = await refreshed;
        expect(response.ok()).toBe(true);
        const snapshot = await response.json();
        expect(snapshot.worker_enabled).toBe(true);
        expect(snapshot.controller_configured).toBe(true);
        if (snapshot.range_busy) {
          await new Promise(resolve => setTimeout(resolve, 1000));
          continue;
        }
        const agent = snapshot.agents.find(a => a.registered && a.active);
        expect(agent).toBeTruthy();
        stage = 'TRAINING_START';
        const started = page.waitForResponse(r => r.url().endsWith('/cyber-range/training/start') && r.request().method() === 'POST');
        await panel.getByRole('button', { name: `Treinar ${agent.name}`, exact: true }).click();
        // Never retry a lost/unknown start response. Only a confirmed busy race is retryable.
        const result = await started;
        expect(result.ok()).toBe(true);
        const body = await result.json();
        if (body.status === 'busy') continue;
        expect(body.status).toBe('queued');
        expect(typeof body.run_id).toBe('string');
        runId = body.run_id;
      }
      if (!runId) { const error = new Error('Laboratory remained busy'); error.code = 'TRAINING_BUSY_TIMEOUT'; throw error; }
      stage = 'TRAINING_FRESH_CYCLE';
      const deadline = Date.now() + 180000;
      while (Date.now() < deadline) {
        const snapshot = await api(context, '/cyber-range/training');
        const run = snapshot.active_run?.id === runId ? snapshot.active_run : snapshot.runs.find(r => r.id === runId);
        if (run?.state === 'COMPLETED') return { fresh_cycle: true, completed: 1 };
        if (run?.state === 'ABORTED') { const error = new Error('New campaign aborted'); error.code = 'TRAINING_FRESH_CYCLE_ABORTED'; throw error; }
        await new Promise(resolve => setTimeout(resolve, 1000));
      }
      const error = new Error('New campaign timed out'); error.code = 'TRAINING_FRESH_CYCLE_TIMEOUT'; throw error;
    });
    await check('Create, authorize and finish a one-step QA mission through the UI', async () => {
      stage = 'CLOSE_VITALS';
      await page.getByRole('button', { name: 'Close system vitals', exact: true }).click();
      stage = 'OPEN_MISSION_FORM';
      await page.getByRole('button', { name: /^Decisions\b/ }).click();
      await page.getByRole('button', { name: 'Criar missão', exact: true }).click();
      stage = 'FILL_MISSION_PLAN';
      const title = `Gauntlet QA mission ${Date.now()}`;
      await page.getByLabel('Título da missão', { exact: true }).fill(title);
      await page.getByLabel('Objetivo da missão', { exact: true }).fill('Validação interna: responder em texto que dois mais dois é quatro. Não solicitar ferramentas, capacidades ou ações externas.');
      await page.getByLabel('Estratégia', { exact: true }).fill('Uma resposta textual curta, sem efeitos externos.');
      await page.getByLabel('Título da etapa 1', { exact: true }).fill('Validar resposta textual');
      await page.getByLabel('Descrição da etapa 1', { exact: true }).fill('Responda apenas: quatro. Não use ferramentas ou capacidades e não execute ações externas.');
      const universes = await api(context, '/universes');
      const agents = await api(context, '/agents');
      const universe = universes.find(u => u.active && agents.some(a => a.active && a.universe_id === u.id) && /engineer/i.test(u.code))
        ?? universes.find(u => u.active && agents.some(a => a.active && a.universe_id === u.id));
      expect(universe).toBeTruthy();
      await page.getByLabel('Universe da etapa 1').selectOption(universe.code);
      stage = 'CREATE_AND_VALIDATE_MISSION';
      await page.getByRole('button', { name: 'Revisar criação e plano' }).click();
      await page.getByRole('button', { name: 'Confirmar criação e validação' }).click();
      await expect(page.getByText('Missão validada. Aguardando sua autorização.', { exact: true })).toBeVisible();
      const article = page.locator('article').filter({ has: page.getByText(title, { exact: true }) });
      stage = 'AUTHORIZE_MISSION';
      await article.getByRole('button', { name: 'Autorizar e iniciar' }).click();
      await article.getByRole('button', { name: 'Confirmar início' }).click();
      const mission = (await api(context, '/missions')).find(m => m.title === title);
      expect(mission).toBeTruthy();
      stage = 'EXECUTE_MISSION';
      await waitForMission(context, mission.id);
      const tasks = await api(context, `/missions/${mission.id}/tasks`);
      expect(tasks.every(task => task.status === 'SUCCEEDED')).toBe(true);
      return { tasks: tasks.length };
    });
    await check('Twelve Universes execute sequential internal text tasks', async () => {
      const universes = (await api(context, '/universes')).filter(u => u.active);
      expect(universes.length).toBe(12);
      const title = `Gauntlet QA twelve Universes ${Date.now()}`;
      const objective = 'Validação interna e textual dos doze Universes. Cada etapa deve responder apenas quatro, sem ferramentas, capacidades, redes públicas ou efeitos externos.';
      const source = await api(context, `/conversations/${conversation.id}/messages`, 'POST',
        { content: `${title}\n${objective}`, client_message_id: randomUUID(), metadata: {} });
      const inception = await api(context, '/inceptions', 'POST',
        { conversation_id: conversation.id, source_message_id: source.id, title, description: objective });
      await api(context, `/inceptions/${inception.id}/submit`, 'POST');
      await api(context, `/inceptions/${inception.id}/approve`, 'POST', {});
      const mission = await api(context, '/missions', 'POST', { inception_id: inception.id, title, objective });
      await api(context, `/missions/${mission.id}/plan`, 'POST', {
        strategy: 'Doze etapas textuais em sequência, sem efeitos externos.', completion_criteria: {},
        steps: universes.map((u, i) => ({ step_key: `qa_${i + 1}`, title: `QA ${u.code}`,
          description: 'Responda apenas: quatro. Não use ferramentas ou capacidades e não realize ações externas.',
          universe: u.code, position: i + 1, depends_on: i ? [`qa_${i}`] : [], completion_criteria: {} })),
      });
      await api(context, `/missions/${mission.id}/validate`, 'POST');
      await api(context, `/missions/${mission.id}/start`, 'POST');
      await waitForMission(context, mission.id);
      const tasks = await api(context, `/missions/${mission.id}/tasks`);
      expect(tasks.length).toBe(12);
      expect(new Set(tasks.map(t => t.universe_id)).size).toBe(12);
      expect(tasks.every(t => t.status === 'SUCCEEDED')).toBe(true);
      return { universes: 12, succeeded_tasks: tasks.length, external_actions: false };
    });
  }
  await check('Secondary service failure preserves real DEUS chat', async () => {
    const isolated = await browser.newContext({ permissions: ['microphone'] });
    await isolated.route('**/api/v1/system/projections', route => route.abort('failed'));
    const { page: degraded, conversation: c } = await open(isolated, `Gauntlet network QA ${Date.now()}`);
    const response = degraded.waitForResponse(r => r.url().endsWith(`/conversations/${c.id}/deus`) && r.request().method() === 'POST');
    await degraded.getByLabel('Message DEUS').fill('Responda apenas: teste concluído');
    await degraded.getByRole('button', { name: 'Send to DEUS' }).click();
    expect((await response).ok()).toBe(true);
    await expect(degraded.locator('.deus-message').last()).toContainText(/teste conclu[ií]do/i);
    await isolated.close();
  });
  await context.close();
  await browser.close();
  browser = null;
  await check('Synthetic microphone → wake word → STT → DEUS → returned PCM', async () => {
    const audioPath = join(workspace, 'qa-microphone.wav');
    await writeFile(audioPath, wav(Buffer.from(credentials.audio_base64, 'base64')));
    const voiceBrowser = await chromium.launch({ args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream',
      `--use-file-for-fake-audio-capture=${audioPath}%noloop`, '--autoplay-policy=no-user-gesture-required'] });
    try {
      const voiceContext = await voiceBrowser.newContext({ permissions: ['microphone'] });
      const conversation = await api(voiceContext, '/conversations', 'POST', { title: `Gauntlet voice QA ${Date.now()}` });
      await voiceContext.addInitScript(({ token, id }) => {
        localStorage.setItem('creation_access_token', token); localStorage.setItem('creation_conversation_id', id);
      }, { token: credentials.access_token, id: conversation.id });
      const p = await voiceContext.newPage();
      const events = []; let reply = ''; let microphoneFrames = 0;
      p.on('websocket', ws => ws.on('framereceived', frame => {
        try {
          const event = JSON.parse(String(frame.payload));
          events.push(event.type);
          if (event.type === 'text_delta') reply += event.text;
        } catch { /* Binary audio frames are counted by server events. */ }
      }));
      p.on('websocket', ws => ws.on('framesent', frame => {
        try { if (JSON.parse(String(frame.payload)).type === 'audio') microphoneFrames++; } catch { /* no payload logging */ }
      }));
      await p.goto(root, { waitUntil: 'domcontentloaded' });
      await p.getByLabel('Message DEUS').click();
      try { await expect.poll(() => events.includes('wake_detected'), { timeout: 45000 }).toBe(true); }
      catch {
        const failure = new Error('Voice wake failed'); failure.name = 'VoiceWakeFailed';
        failure.code = microphoneFrames ? 'MICROPHONE_FRAMES_WITHOUT_WAKE' : 'NO_MICROPHONE_FRAMES';
        throw failure;
      }
      await expect.poll(() => events.includes('transcript_commit'), { timeout: 45000 }).toBe(true);
      await expect.poll(() => events.includes('audio_chunk'), { timeout: 45000 }).toBe(true);
      await expect.poll(() => /quatro|\b4\b/i.test(reply), { timeout: 45000 }).toBe(true);
      return { synthetic: true, wake: true, transcript: true, pcm_response: true };
    } finally { await voiceBrowser.close(); }
  });
} finally {
  if (browser) await browser.close();
  credentials.access_token = ''; credentials.audio_base64 = '';
  await rm(workspace, { recursive: true, force: true });
}
const failed = results.filter(r => !r.ok).length;
console.log(JSON.stringify({ suite: 'live-gauntlet', passed: results.length - failed, failed,
  physical_microphone_validated: false, minio_storage_validated: false }));
process.exitCode = failed ? 1 : 0;
