# THE CREATION OS Architecture

## Immutable flow

```text
Creator -> Creator Interface -> DEUS / SOPHIA / ROCKMAM -> Inception
        -> Central Core -> Tree Core -> Universes -> Agents
        -> Tree Core -> Central Core -> Malkuth
```

## Tree Core Foundation v0.4.1

Tree Core currently owns only agent discovery and capability-based selection.
The Agent Registry persists agent identity, universe label, lifecycle state,
priority, heartbeat, and normalized capabilities. The Capability Engine checks
an authorized Mission and returns eligible agents ordered by priority.

Eligibility requires:

- enabled agent;
- `idle` status;
- every requested capability;
- heartbeat no older than five minutes.

Tree Core does not create, approve, authorize, dispatch, execute, aggregate, or
manifest Missions. Dispatch, Execution, Aggregation, complete Universes, Pulse,
and Malkuth remain outside v0.4.1.

## Mission Planner v0.4.2

An authorized Mission is a strategic objective. The deterministic planner creates
a cycle-free Task DAG. Tasks are operational planning units. Dispatch and execution
do not exist in this version.

## Dispatch Queue v0.4.3

The queue persists future Task routing decisions after Capability Engine matching.
Leasing uses PostgreSQL row locks and opaque high-entropy tokens stored only as
SHA-256 hashes. The queue has no worker and performs no execution.

## Agent Dispatcher Protocol v0.4.4

**STATUS: FROZEN.** The Agent Dispatcher remains a protocol-only boundary. No
runtime, polling, worker process, Agent invocation, Task execution, Mission
execution, or manifestation belongs to this version.

The Agent Dispatcher is a protocol boundary after Dispatch Queue. Persistent
workers announce normalized capabilities and authenticate with opaque credentials.
A claim returns a lease-bound Execution Envelope; it never invokes an Agent.
Heartbeat never renews a lease, and retry, timeout, or shutdown grants no authority.
There is no runtime, permanent worker, scheduler, automatic processing, or
manifestation in this version.

## Agents v0.4.5

Controlled execution belongs to the existing Agents block. Dispatch Queue and
Agent Dispatcher remain internal mechanisms between Capability Engine and Agents.
Only registered deterministic handlers with no side effects can run. Every result
returns to Tree Core; Malkuth remains responsible for manifestation.

## Central Core Decision

Central Core reads Tree Core mission consolidations and records immutable
decisions. It does not change Mission, Task, DispatchItem, AgentExecution, or
MissionConsolidation records. A recorded decision becomes available for later
policy reasoning and Malkuth manifestation.

## DEUS, SOPHIA, ROCKMAM

DEUS conversation, SOPHIA understanding, and ROCKMAM assessment are separate
bounded steps. They may interpret, understand, and assess, but they do not create
Mission automatically and do not bypass Creator authorization.

## Memory, Automation, Opportunity, Perception

Memory provides Creator context. Automation connectors remain capability-governed.
Opportunity Discovery and Continuous Perception may collect, rank, notify, and
support Creator review, but they do not authorize Mission and do not manifest.

## Release Candidate Boundary

The release-candidate health boundary is Alembic `0024_creator_singleton`.
Readiness requires PostgreSQL, Redis, and the expected migration revision. This
document records architecture only; it does not authorize new layers, engines,
workers, endpoints, or responsibility shifts.

## Creator Interface — Living Universe Motion

The initial Creator Interface screen (`frontend/src/components/LivingDashboard.tsx`)
renders the universe as a single `<canvas>` driven by one `requestAnimationFrame`
loop (`LivingUniverseScene`), not a static image. This is the already-accepted
direction on this branch (see commit history and `docs/AUDIT_v0.5.md`); the
sidebar-vs-universe boundary the spec actually protects (no persistent
sidebar/menu/dashboard-grid) remains untouched and is guarded by
`frontend/src/components/LivingDashboard.frozenSpec.test.ts`.

**Documentation debt resolved (2026-07-31):** `docs/CREATOR_INTERFACE_FROZEN_SPEC.md`
previously described a static-image base (`frontend/public/creator-interface-approved-universe.png`)
and explicitly forbade a procedural Canvas — text left over from commit
`398835d`, never updated when `0fc8821` ("restore functional living universe")
made the canvas the accepted implementation. The spec's Source Of Truth,
Initial State, and Acceptance Criteria sections were rewritten to describe the
canvas/`requestAnimationFrame`/`prefers-reduced-motion` behavior actually in
place, and a Changelog section was added to the spec itself so this reasoning
stays traceable there going forward. The Permanent Elements and Forbidden
Elements sections (the actual sidebar/menu/dashboard-grid boundary) were left
byte-for-byte unchanged — this was a documentation-only fix, no design
decision was reopened.

Taste calls made while adding continuous motion (all chosen for the most
subtle, reversible value, per the batch's own instruction not to stop and ask):

- **Canvas motion** (particle drift, hotspot orbit/breathing, constellation
  twinkle, neural-path signal travel) was already implemented before this
  batch; this batch only made `prefers-reduced-motion` reactive to a live OS
  toggle instead of a mount-time-only check (a `MediaQueryList` `change`
  listener updates a closured `reducedMotion` flag read by the existing draw
  loop; cleaned up alongside the existing `ResizeObserver`/`pointermove`
  cleanup).
- **DOM finishing touches** added on top of already-existing elements only
  (no new structural elements): a 7s opacity/scale breathing loop on the DEUS
  label, a 2.6s pulse on the chronicle-ticker status dot, a 5s opacity
  breathing loop on the system-state-binding pill (only while
  `loadState === "ready"`, i.e. only when genuinely healthy), a 600ms
  `stroke-dasharray` transition on the pulse-score ring so score changes
  glide instead of snapping, a 120ms opacity fade on the hotspot tooltip, and
  a 420ms fade/scale-in on constellation cards (covers a universe card
  appearing when a universe goes active).
- All new animations use `transform`/`opacity` (or, for the pulse-score ring,
  an infrequent data-driven SVG attribute transition, not a per-frame one) —
  no `width`/`height`/`top`/`left` animation was added.
- All new CSS animations are covered by the existing global
  `@media (prefers-reduced-motion: reduce)` rule
  (`frontend/src/styles/living-dashboard.css`), which already zeroes
  `animation-duration` for every element; no per-animation opt-out was
  needed.
- No new animation dependency was added. `@types/node` was added as a
  dev-only dependency so the new frozen-spec regression test can read source
  files with `node:fs`; it has no runtime/bundle effect (confirmed by
  `npm run build` output).

## Creator Interface — On-Demand Overlays (corporate-dashboard reference, overlay-only delivery)

The Creator supplied a reference image styled as a fixed two-column corporate
dashboard (permanent left/right panels). Per `docs/CREATOR_INTERFACE_FROZEN_SPEC.md`,
none of that layout is implemented as permanent — every content block from the
reference became content inside the existing single on-demand overlay
(`{demandPanel}`, one panel at a time, closed by default), reachable via a new
row of shortcut pills in the conversation dock and two new header icon
triggers. No second overlay slot was added; opening any panel still replaces
whichever one was open, exactly as `LivingDashboard.frozenSpec.test.ts` already
enforces.

Overlay-to-content mapping (all wired through the existing `requestedPanel`/
`RequestedPanel` mechanism in `appLogic.ts`):

- **Mostrar Inceptions** (pill) → existing `InceptionPanel`.
- **Mostrar Missões** (pill) → existing `MissionAuthorizationPanel`, now
  preceded by an `OverlayStatsRow` carrying the reference image's "Informações
  Ativas" block (missões ativas, oportunidades, agentes online, capabilities
  ativas, percepção ativa) and "Foco Atual" (active mission title + a progress
  bar). The bar's percentage is **not** a fabricated number: it comes from
  `missionProgressFraction(status)`, a fixed mapping of the mission's real
  status onto its position in the `drafted → ... → manifested` stage sequence
  already defined in `backend/app/core/domain.py`.
- **Mostrar Oportunidades** (pill) → existing `OpportunityPanel`.
- **Abrir Universo** (pill) → existing inline Universos/Agentes overlay in
  `App.tsx`; each agent row now shows a real online/offline status dot
  (`agent.enabled` + non-idle/offline/disabled status — the same rule already
  used for canvas activity states, not a new heuristic).
- **Mostrar Percepção** (pill) → existing `PerceptionPanel`.
- **Mostrar Capabilities** (pill) → existing `CapabilityPanel`.
- **Mostrar Auditoria** (pill) → existing `ChronicleRibbon`, now preceded by
  an `OverlayStatsRow` for the reference image's "Autorizações" block
  (Inceptions pendentes, Missão aguardando autorização, Notificações não
  lidas). "Missão aguardando autorização" is deliberately scoped to the one
  `MissionAuthorization` record the app already loads (for the active
  mission) rather than fabricating a cross-mission "decisões pendentes"
  count the backend doesn't expose to this client today — see Ambiguity note
  below.
- **Notification bell icon (header)** → new `NotificationsPanel`, the full
  notification history (the pre-existing `real-notification-layer` transient
  corner toast for unread notifications is untouched — this overlay is the
  "Ver todas" destination from the reference image).
- **Search icon (header)** → new `SearchPanel`. Client-side substring search
  over data already loaded from the real API (missions, inceptions,
  opportunities, agents, universes) — there is no backend search endpoint, so
  this filters in-memory state rather than fabricating a network search.
- **Clique em agente/nó ("Agentes em Destaque")** → deliberately **not** a new
  panel. The existing Universos/Agentes overlay (see "Abrir Universo" above)
  already lists every agent with real status; adding per-agent invisible hit
  targets synced to the canvas's procedurally-computed node positions would
  be substantial new canvas-to-DOM plumbing for content that already has a
  reachable, real home. Clicking a universe/agent hotspot already routes here
  via the existing `hotspotSummaries` → `panel: "universes"` mechanism.

Ambiguity note (per this batch's own instruction: choose the most natural
trigger, document, proceed — don't stop and don't go permanent): the
reference image's "Autorizações" block shows three independent pending
counts (Inception / Missões / Decisões). Only Inceptions pendentes is a real,
cheaply-computable global count (`inceptions.filter(pendingInception)`).
Missões and Decisões have no equivalent list-wide endpoint wired into this
client (`missionAuthorization` is fetched only for `missions[0]`, and there
is no "pending decisions" list endpoint consumed here) — fabricating those
two counts from data the app doesn't have would violate this batch's own
"não fabrique número" rule. Shown instead: whether the one loaded mission
authorization is `"pending"` (0 or 1, real) and unread notification count
(real), not a global decisions-pending count.

Visual re-styling within already-existing elements (permitted, not a new
structural element): ROCKMAM's hue/tone changed from gold to blue
(`hue: 208`, `tone: "blue"`) in both `LivingDashboard.tsx`'s canvas hotspot
and `UniverseConstellationLabels.tsx`'s core card, matching the reference
image; the DEUS↔ROCKMAM neural path hue was updated to match.

## Git Rules

### Regra de segurança: git stash

Motivo: em 2026-07-31, um `git stash push --keep-index` seguido de um
comando (`tsc --noEmit`) que excedeu o timeout da ferramenta e foi morto
no meio corrompeu o `git stash pop` seguinte. Dois arquivos
(voice.ts, types.ts) reverteram silenciosamente para o conteúdo do HEAD
— sem aparecer no `git status`, porque o conteúdo revertido era idêntico
ao já commitado. Só foi detectado porque um `tsc --noEmit` final, já
fora do stash, acusou erro de tipo.

Regras obrigatórias daqui em diante:

1. Nunca rodar um comando com risco de timeout (builds, typecheck,
   testes completos, comandos de rede) enquanto um stash estiver
   aberto (entre `git stash push` e `git stash pop`). Fazer o stash,
   sair da janela de risco, e só então rodar comandos potencialmente
   longos — fora do stash.
2. Após qualquer `git stash pop`, antes de confiar no resultado,
   comparar explicitamente o conteúdo restaurado contra uma referência
   confiável (`git diff stash@{0} HEAD` ou equivalente) — nunca
   confiar apenas em `git status` limpo como prova de que nada mudou,
   já que uma reversão para conteúdo idêntico ao HEAD não aparece lá.
3. Preferir alternativas mais seguras ao stash quando o objetivo for
   apenas inspecionar o índice isoladamente: `git diff --cached`,
   worktrees separadas (`git worktree add`), ou branches temporárias —
   reservar `git stash` para quando não houver alternativa mais segura.
4. Se um comando rodado durante uma janela de stash aberto travar ou
   for interrompido por timeout, tratar isso como incidente: não
   prosseguir para o próximo passo do lote sem antes verificar
   arquivo por arquivo (diff) que nada foi perdido ou revertido
   silenciosamente.

## Lote 2.6 — Auditoria confirma sem gap de código (2026-08-01)

Reauditado a pedido do Criador. Nenhum arquivo de código foi alterado
neste lote — os critérios de aceitação já estavam satisfeitos pelo
trabalho registrado em `9c8835f` (`feat(universe): seed 12 Universes,
gate agent eligibility, add 3 handlers`) e reconfirmados agora com
testes reais (`40 passed` no subconjunto relevante, `ruff check` limpo,
consulta direta ao Postgres do `docker compose` mostrando os 3
Universos ativos com exatamente 1 Agent + 1 Capability cada).

Duas decisões de gosto registradas em vez de código novo:

- **`Agent.capabilities_json` permanece `{}`.** Essa coluna JSON existe
  no modelo (`app/models/entities.py`) mas não é o mecanismo real de
  vínculo de capability — isso é `agent_capabilities` (tabela relacional
  N:N via `Capability`), que a migration `0023_universe_agent_seed`
  já popula corretamente e que `TreeCoreRepository.eligible_agents()`
  já consulta. `capabilities_json` é `{}` para *todo* Agent do sistema,
  inclusive os criados pela rota administrativa real
  (`TreeCoreService.register_agent`, `app/services/tree_core.py:45`) —
  não é uma lacuna específica destes 3 agentes. Preenchê-la agora só
  para estes três criaria uma inconsistência nova (esses três teriam
  dado que nenhum outro Agent do sistema tem, duplicando — e podendo
  divergir de — a fonte real de verdade). Deixado como está.
- **`KnowledgeResearchAgent` não consulta `MemoryService`.** O contrato
  congelado do Handler Registry v0.4.5 (`docs/AGENTS_V045_AUDIT.md`)
  exige que `ExecutionContext` não carregue sessão de banco, credencial
  nem I/O — e `MemoryService` (`app/services/memory.py`) é um serviço
  que exige repositório/sessão para funcionar. Ligar os dois exigiria
  ou quebrar o contrato do Handler Registry ou avançar sobre o Lote 2.5
  (Memória), ambos fora do escopo autorizado deste lote. O handler já
  documenta essa fronteira no próprio docstring
  (`backend/app/agents/handlers.py`, `knowledge_research`).

## Lote 2.5 — Memória em quatro camadas (2026-08-01)

### Auditoria: o que já existia

As quatro tabelas (`conversation_memory`, `mission_memory`, `universe_memory`,
`conscious_memory`) e seus modelos ORM já existiam desde `0001_initial` —
nunca referenciadas em nenhum repositório, service, rota ou teste antes deste
lote (`grep` exaustivo confirmou zero hits fora de `entities.py`). Um quinto
sistema de memória, `CreatorMemory` (`creator_memories`, migration `0016`),
já é completo (repositório, service, rota, testes) mas é **imutável por
trigger de banco** e não é uma das quatro camadas deste lote — não foi
tocado. `EmbeddingModel`/`LanguageModel` (Protocols) e `FakeEmbeddingModel`/
`FakeLanguageModel` já existiam em `app/ai/`, reutilizados sem duplicação,
conforme pedido.

Achado real durante a auditoria: `ConsciousMemory.embedding` estava
declarado como `JSON` no modelo SQLAlchemy, mas a migration `0001_initial`
cria a coluna como `psql.ARRAY(psql.REAL())` (Postgres `real[]`) — um
mismatch nunca exercitado porque nada lia/escrevia a coluna antes. Corrigido
para `postgresql.ARRAY(postgresql.REAL())`, sem nova migration (a coluna já
existe nesse formato desde o início).

### Padrão escolhido para a lacuna do KnowledgeResearchAgent (seção 2)

**Padrão (a), implementado sem alterar `ExecutionContext`.** O ponto de
injeção real não é o Tree Core nem o worker diretamente — é
`AgentExecutionService.run()` (`backend/app/services/execution.py`), que já
tem sessão de banco (é um service normal, não um handler) e é o único lugar
que monta o payload antes de chamar `registry.invoke()`. Para a capability
`knowledge_research`, `run()` agora resolve memória via
`ConsciousMemoryService.search()` *antes* de invocar o handler e injeta o
resultado já materializado (strings, não uma conexão) dentro do payload —
especificamente em `notes`, o mesmo campo que o handler já tratava
genericamente. `ExecutionContext` continua exatamente como estava (nenhum
campo novo); `knowledge_research` em `handlers.py` continua **byte a byte
idêntico** — puro, determinístico, sem I/O, exatamente como o contrato
v0.4.5 exige. `test_handler_registry_contract.py` (novo) fixa essa fronteira
como regressão: falha se `ExecutionContext` algum dia ganhar um campo que
pareça sessão/conexão/repositório/credencial.

Rejeitado: padrão (b) (MemoryReader Protocol dentro do
ExecutionContext) — mesmo sendo "só uma interface", carregar qualquer
objeto vivo dentro de um dataclass frozen que os handlers recebem abriria
superfície para I/O dentro do handler no futuro (alguém chamando
`context.memory.search(...)` de dentro de uma função que deveria ser pura).
O padrão (a) resolve o mesmo problema sem essa superfície nova.

### Decisões de gosto

- **Busca em `conscious_memory` é ranking em Python (cosine similarity),
  não pgvector real.** A extensão `vector` está instalada
  (`0022_pgvector_extension`) mas a coluna `embedding` continua `real[]`,
  não o tipo `vector` — migrar o tipo de coluna e adicionar índice ANN é
  uma mudança de schema maior, fora do escopo "simples e reversível" deste
  lote. `ConsciousMemoryRepository.search_by_embedding` busca até 500
  candidatos e ordena em Python — documentado como limitação de escala no
  próprio docstring do repositório, não escondido atrás de uma interface
  que finge ser indexada.
- **`chronicle_embedding_dim` renomeado para `conscious_memory_embedding_dim`
  e ligado a `CONSCIOUS_MEMORY_EMBEDDING_DIM`.** Era uma constante morta
  (nunca lida em lugar nenhum, nome errado — Chronicles não usa embeddings).
  Reaproveitada em vez de criar uma nova, e agora genuinamente configurável
  por variável de ambiente como o prompt pediu; `ConsciousMemoryService`
  valida a dimensão real do embedding contra ela antes de gravar.
- **`ScopedMemoryRepository` é genérico (uma implementação, três tabelas).**
  `conversation_memory`/`mission_memory`/`universe_memory` têm forma
  idêntica (id, `<pai>_id`, key, value_json, timestamps) — uma classe
  parametrizada por modelo + atributo de FK evita triplicar o mesmo CRUD.
  Nenhuma das três tem `UNIQUE(parent_id, key)` no schema já existente;
  `set`/upsert faz find-then-update-or-insert em nível de aplicação em vez
  de uma migration nova para adicionar a constraint — reversível, e uma
  migration de unicidade pode vir depois se colisões concorrentes
  aparecerem na prática.
- **`consolidate_from_mission` não commita; `consolidate_explicit`
  commita.** A primeira roda dentro da transação de
  `ManifestationService.manifest()` (um rollback da manifestação também
  desfaz a memória consolidada); a segunda é uma chamada autônoma. Essa
  assimetria está documentada no docstring de `ConsciousMemoryService`
  para não ser reintroduzida por engano.
- **Nenhuma rota HTTP nova.** O prompt não pediu exposição via API — os
  quatro stores são acessíveis via service layer (e, para
  `knowledge_research`, automaticamente via execução real de tarefa).
  `consolidate_explicit` fica pronto para ser chamado por uma rota futura
  quando o Criador quiser expor "decisão explícita de persistir
  conhecimento" como uma ação real da interface — não construído agora
  para não expandir escopo.

### Arquivos criados
- `backend/app/core/memory_store.py` — Protocol `MemoryStore`.
- `backend/app/repositories/scoped_memory.py`,
  `backend/app/services/scoped_memory.py` — camadas conversation/mission/universe.
- `backend/app/repositories/conscious_memory.py`,
  `backend/app/services/conscious_memory.py` — quarta camada + consolidação.
- `backend/tests/test_scoped_memory.py`, `test_conscious_memory.py`,
  `test_conscious_memory_consolidation_triggers.py`,
  `test_handler_registry_contract.py`, `test_knowledge_memory_integration.py`.

### Arquivos alterados
- `backend/app/models/entities.py` (tipo da coluna `embedding`).
- `backend/app/config.py` (renomeia/liga a dimensão do embedding).
- `backend/app/services/execution.py` (injeção de memória pré-invocação).
- `backend/app/services/manifestation.py` (gatilho (i) de consolidação).

## Auditoria: Tree Core, Agentes, Malkuth (2026-08-01)

### Achado que redefine o escopo: a fila de dispatch não é Redis Streams
O prompt original desta auditoria presumia "Redis Streams consumer
groups" como o mecanismo de dispatch. Não é. `grep` confirma Redis
Streams só existe em `app/api/creator_interface.py` e
`app/schemas/pulse.py` (relato de saúde do Pulse). O mecanismo real —
e o único que existe — é baseado em Postgres: `dispatch_items` com
`lease_owner`/`lease_token_hash`/`lease_expires_at`/`version`, lock de
linha (`with_for_update`) e reclaim expresso em SQL dentro de
`DispatchService.lease()` (`app/services/dispatch.py`). Não há
consumer group, `XCLAIM`, nem "pending entries list" em lugar nenhum
do código — essa parte da auditoria não se aplica à arquitetura real e
fica registrada aqui em vez de forçar um resultado.

### P4 — Reclaim de lease sob concorrência real
A lógica de reclaim (SQL que readquire itens com `lease_expires_at`
expirado) já é exercitada por
`test_dispatch_error_paths_expiration_acknowledge_and_release`
(`tests/test_dispatch_integration.py`) — expira o lease manualmente e
confirma que `lease()` o readquire para um novo worker. Isso prova a
correção da query. O que falta, e continua faltando, é o cenário com
dois processos `python -m app.worker` reais disputando o mesmo lease
via wall-clock real — nenhum teste do repositório spawna
`app.worker` como subprocesso (`grep -rn "subprocess\|Popen.*app.worker"`
não retorna nada). Avaliado como um gap de **realismo de teste**, não
de lógica: a lógica está correta e testada; só a integração via
processo-SO real nunca foi exercitada. Escrever esse teste (spawn de
2 processos reais, `WORKER_CREDENTIAL_FILE`, banco de teste
compartilhado, timing de wall-clock) é trabalho de infraestrutura de
teste não-trivial e frágil o suficiente para justificar reportar antes
de implementar, em vez de presumir que "auditoria" autoriza construir
isso agora. Fica pendente, aguardando decisão do Criador sobre
prioridade.

### P5 — Retry/backoff sob processo real
`DispatchService.fail()` já implementa o backoff exponencial real
(`retry_delay(base, attempt_count, maximum)`, RETRY_SCHEDULED até
`max_attempts`, DEAD_LETTERED depois, com falha da Mission e evento
`mission_failed` no mesmo commit). Mesma situação do P4: a lógica é
real e testada em processo único; falta um teste via processo de
worker separado observando o atraso de fato. Mesmo tratamento: reportado,
não implementado, mesma razão (infraestrutura de teste não-trivial).

### Gap real e pequeno, corrigido: handler ausente não falhava graciosamente
Confirmado um gap real e corrigido diretamente (padrão já existente,
sem mudança estrutural): `app/worker.py::_execute()` capturava
`HandlerError` (nenhum handler registrado para a capability da Task) e
chamava `workers.release()` — que devolve o item para `QUEUED` sem
tocar `attempt_count`. Resultado: um item cuja capability nunca teve
handler ficava sendo reclamado e falhando silenciosamente para sempre,
sem nunca consumir uma tentativa, nunca dead-letterar e nunca refletir
na Mission. Corrigido trocando `workers.release(...)` por
`dispatch.fail(dispatch_id, worker.worker_uuid, token,
"no_handler_registered", ...)` — reaproveita o mecanismo de
fail/backoff/dead-letter/`mission_failed` já existente e testado, sem
inventar um novo. Teste novo:
`test_worker_execute_fails_gracefully_when_no_handler_is_registered`
(`tests/test_worker_orchestration.py`), que chama `app.worker._claim()`
e `_execute()` de verdade (monkeypatch de `AsyncSessionLocal` para o
engine isolado do teste e de `settings.worker_credential`), e confirma
`state == "dead_lettered"`, `attempt_count == 1`, Mission `failed`, evento
`mission_failed`.

### Malkuth — as 3 preconditions são reais, não placeholder
- **(i) Tasks completas**: verificado em `ConsolidationService.consolidate`
  → `build_consolidation()` (`app/core/consolidation.py`), que levanta
  `ConsolidationError` se qualquer Task não tiver exatamente 1 execução
  terminal bem-sucedida. Testes extensos em `tests/test_consolidation.py`.
- **(ii) Central Core validado**: `evaluate_decision()`
  (`app/core/decision.py`) só aprova (`APPROVED`) quando a Consolidation
  referenciada está `complete`, sem inconsistências, com contagem de
  Tasks batendo e fingerprint válido — senão `REQUIRES_REVIEW`.
  `ManifestationService.manifest()` exige `decision.decision ==
  "APPROVED"` e fingerprint válido antes de manifestar
  (`app/services/manifestation.py:51-54`).
- **(iii) Sem falha crítica pendente**: não é um terceiro check
  redundante — é estrutural, pela cadeia Consolidation→Decision: uma
  Task com falha definitiva já transiciona a Mission para `FAILED`
  dentro de `DispatchService.fail()` (dead-letter), e uma Mission
  `FAILED` nunca mais passa por `require_malkuth_authorized()` (gate em
  `manifest()`/`consolidate()`/`decide()`), então o fluxo nunca chega a
  produzir uma Decision `APPROVED` para ela. Confirmado por
  `test_tail_orchestration_never_runs_for_a_failed_mission`
  (`tests/test_worker_orchestration.py`), que já prova a recusa
  ponta-a-ponta.
- **Chronicle e memória consolidada**: o evento real é
  `mission_manifested` (não `malkuth.manifested`, que o prompt original
  presumia) e o gatilho real de memória consolidada é
  `ConsciousMemoryService.consolidate_from_mission()` (não
  `consolidate_explicit()`, que é o gatilho (ii) — decisão explícita do
  Criador, um caminho independente). Ambos já implementados no Lote 2.5
  e cobertos por `test_manifestation_consolidates_exactly_once_and_only_on_first_success`
  (`tests/test_conscious_memory_consolidation_triggers.py`).

### Agentes — regressão confirmada, sem gap novo
- Contrato de saída tipado dos 3 handlers: inalterado desde o Lote 2.5
  (`app/agents/handlers.py` byte-a-byte idêntico), confirmado pela
  suíte de regressão completa incluindo `test_handler_registry.py` e o
  novo `test_handler_registry_contract.py` (guarda literal contra
  reintrodução de sessão/credencial em `ExecutionContext`).
- `SecurityReviewAgent`: a checagem contra `SENSITIVE_KEYS`
  (`app/repositories/domain.py`) é enforcement real — o handler marca
  `status: "blocked"`/inclui os achados no `Result`, e é esse status
  que o restante do fluxo (execução/consolidação) trata como não
  bem-sucedido; não é um relatório ignorado.
- `EngineeringDesignAgent`: confirmado sem `subprocess`/`eval`/`exec`
  nem qualquer I/O — decomposição pura de string/dicionário.
- `KnowledgeResearchAgent`: a integração com `ConsciousMemoryService`
  via `AgentExecutionService._resolve_memory_context()` (padrão (a) do
  Lote 2.5) é exercitada em produção — todo `run()` para a capability
  `knowledge_research` passa por esse caminho, não só em teste isolado.

### Arquivos alterados
- `backend/app/worker.py` (handler ausente usa `dispatch.fail()`, não
  `workers.release()`).
- `backend/tests/test_worker_orchestration.py` (fixture
  `unregistered_capability_mission_db` + teste do gap acima).

## Auditoria: GOD e SOPHIA (2026-08-01)

Nenhuma mudança de comportamento nesta rodada — auditoria pura. Achados:

- **Roteamento (`classify_message`, `app/core/god.py`) é 100%
  determinístico** (três listas fixas de termos), sem chamada a LLM em
  produção. `LanguageModel`/`EmbeddingModel` (`app/ai/interfaces.py`)
  só são usados por `ConsciousMemoryService` (embeddings do Lote 2.5) —
  nenhum código de GOD/SOPHIA os importa. `.env.example` já vem com
  `LLM_PROVIDER=fake`/`LLM_MODEL=fake`, e não existe nenhuma classe de
  provider real no repositório (só `FakeLanguageModel`/
  `FakeEmbeddingModel` em `app/ai/fake.py`).
- **GOD consulta memória real** (`GodConversationService._memory_context`,
  todo `interact()`), mas via `CreatorMemory`/`MemoryRepository`
  (`app/core/memory.py`) — um sistema pré-existente e **distinto** do
  `conversation_memory` do Lote 2.5 (`ScopedMemoryRepository`). As duas
  camadas coexistem sem ligação entre si; nenhuma foi alterada aqui.
  Janela real: até 50 candidatos por `importance>=1`, reduzidos aos 5
  mais relevantes via `select_memory_context`.
- **`SYSTEM_QUERY` não existe** — `GodInteractionType` tinha só
  `DIRECT_RESPONSE`/`INFORMATIONAL`/`POTENTIAL`/`UNSUPPORTED` (ver Lote
  SYSTEM_QUERY abaixo para o fechamento desse gap).
- **Schema real de saída de SOPHIA** (`SophiaUnderstandingDocument`,
  `app/core/sophia.py`) não tem `missing_information`, `confidence` nem
  `should_propose_inception` — campos que nunca existiram no código
  (confirmado por busca no repositório inteiro). O schema real é
  `understanding_type` / `boundaries` (`decides`, `manifests`,
  `executes`, `creates_inception`, `creates_mission` — todos sempre
  `False`, incondicionalmente) / `signals`.
- **A garantia "SOPHIA nunca propõe operação sem ROCKMAM validar" é
  real, e mais forte do que o desenho original presumia**: não depende
  de nenhum campo de confiança nem de decisão do LLM — é estrutural em
  duas camadas independentes. SOPHIA nunca seta nenhuma `boundary` como
  operacional (hardcoded `False`), e `boundaries_are_non_operational()`
  (`app/core/rockmam.py`) audita esse mesmo invariante e força
  `NOT_VIABLE` se qualquer `boundary` algum dia vier `True`. Mesmo que
  SOPHIA fosse alterada no futuro para tentar propor uma operação,
  ROCKMAM bloquearia estruturalmente, não por convenção.

Nenhum documento do repositório continha essas 5 divergências por
escrito — elas vinham de um prompt de design externo (colado
diretamente na conversa, não versionado neste repositório). Esta seção
é o registro vivo que as corrige. `docs/PROMPT_INCREMENTO_COMPLETO.md`
(linha ~182) ainda menciona `malkuth.manifested` como nome hipotético
de evento para uma feature futura de consolidação de memória — esse
arquivo é um artefato histórico de prompt (mesma categoria do "v0.3"),
não um documento vivo, então não foi editado; a informação correta
(`mission_manifested`, já implementado no Lote 2.5) vive aqui e na
seção "Auditoria: Tree Core, Agentes, Malkuth" acima.

## SYSTEM_QUERY — 5ª rota de GOD (2026-08-01)

Fecha o gap de `SYSTEM_QUERY` identificado na auditoria GOD/SOPHIA
acima. `GodInteractionType` ganha `SYSTEM_QUERY`; `classify_message()`
reconhece 7 tópicos via o mesmo mecanismo de listas de termos já usado
para as outras 4 categorias (`SYSTEM_QUERY_TOPIC_TERMS`, em
`app/core/god.py`): `pulse`, `missions`, `inceptions`, `memory`,
`universes`, `agents`, `general`. Dado real é resolvido **fora** do
módulo puro `app/core/god.py` — em `GodConversationService._system_snapshot()`
— e injetado, mesmo padrão (a) já usado para `memory_context` e para a
injeção de memória do Lote 2.5: nenhuma sessão de banco entra em
`ExecutionContext` nem em nenhuma função pura de `core/`.

### Colisão real entre "agentes disponíveis" e o termo UNSUPPORTED "agent"
Toda frase do tópico `agents` contém "agente(s)", e `"agent"` já é um
termo de `UNSUPPORTED_TERMS` (bloqueia comandos operacionais como
"execute agent"). Perguntar "quantos agentes estão disponíveis" é uma
intenção de leitura, não uma tentativa de comandar um agente — mas o
classificador só enxerga substring, não intenção. Resolvido com uma
exceção estreita e explícita: só as 4 frases enumeradas do tópico
`agents` (`agentes disponiveis`, `quantos agentes`, `agentes ativos`,
`agentes online`) são checadas antes de `UNSUPPORTED_TERMS`; qualquer
outra menção a "agent" (`execute agent`, `chamar o agente`, etc.)
continua caindo em `UNSUPPORTED` exatamente como antes. Nenhuma outra
categoria mudou de comportamento — comentário equivalente deixado em
`classify_message()`.

### Fonte de dado real por tópico
- **`pulse`/`general`**: reaproveitam `build_pulse_snapshot()`
  (`app/services/pulse.py`, extraído de `GET /api/v1/pulse` — mesma
  lógica, mesma função, chamada dos dois lugares, não duplicada).
- **`missions`**: `GodConversationRepository.mission_counts(creator_id)` —
  contagem total e "em andamento" (`planned`/`authorized`/`distributed`/
  `executing`), escopada ao Creator soberano via `Mission.creator_id`.
- **`inceptions`**: `pending_inception_count(creator_id)` — via join
  `Inception.conversation_id -> Conversation.creator_id`, já que
  `Inception` não tem `creator_id` direto.
- **`universes`**/**`agents`**: `universe_counts()`/`agent_counts()` —
  globais, sem escopo de Creator (essas tabelas não têm essa coluna;
  fazem sentido só como conceito de sistema, não por Criador).
- **`memory`**: `memory_item_counts(creator_id)` — decisão de gosto:
  expõe só contagens (`CreatorMemory` do Criador + `ConsciousMemory`
  global), nunca conteúdo. Não tenta agregar as 3 camadas escopadas do
  Lote 2.5 (`conversation_memory`/`mission_memory`/`universe_memory`)
  porque cada uma é indexada por um `parent_id` específico (uma
  Conversation/Mission/Universe), não por Creator — uma pergunta geral
  de "memória" não tem um escopo natural único para somar essas três
  sem inventar uma nova agregação global que não existe hoje.

### Formato de resposta
Decisão de gosto (ambiguidade da seção 7): cada resposta tem uma
`message` em texto corrido de uma linha (fácil de ler) **e** um campo
estruturado `system_query: {topic, data}` (fácil de testar/auditar —
é isso que os testes de integração comparam, não a string).

### Dois bugs reais encontrados só na validação (não na auditoria)
- **`ck_god_interaction_type` (CHECK constraint no Postgres)**: adicionar
  `SYSTEM_QUERY` ao enum Python `GodInteractionType` não bastava — a
  tabela `god_conversation_interactions` (migration `0013_god_conversation`,
  já aplicada ao banco persistente real, `alembic_version` confirmado em
  `0024_creator_singleton` antes desta mudança) tem uma CHECK constraint
  de banco que hardcoda os 4 valores antigos, independente do enum
  Python. Sem correção, toda interação SYSTEM_QUERY real falhava no
  commit com `asyncpg.exceptions.CheckViolationError`, capturado e
  mal-reportado como `GodConversationError("... could not be persisted
  atomically")`. Corrigido com uma migration nova,
  `0025_god_system_query` (não editando `0013` in-place — já está
  aplicada de verdade). Só foi descoberto porque os testes de
  integração de SYSTEM_QUERY rodaram contra Postgres real, não um
  fake/mock — motivo a mais para nunca substituir esses testes por
  mocks.
- **`SOPHIA.UNDERSTANDING_BY_GOD_TYPE` sem entrada para `SYSTEM_QUERY`**:
  `build_understanding()` (`app/core/sophia.py`) faz um lookup direto
  nesse dict sem fallback — uma interação SYSTEM_QUERY chegando a
  `SophiaService.understand()` levantaria `KeyError` não tratado.
  Nenhum teste hoje encaminha uma interação SYSTEM_QUERY para SOPHIA (o
  fluxo real de SYSTEM_QUERY responde e termina dentro de GOD), mas o
  gap era real e silencioso. Corrigido adicionando
  `SYSTEM_QUERY_UNDERSTANDING` ao enum `SophiaUnderstandingType` e ao
  dict, mesmo padrão das outras 4 entradas — ROCKMAM já trata qualquer
  `understanding_type` não explicitamente bloqueado como `VIABLE`
  (nenhuma mudança necessária em `app/core/rockmam.py`).

### Achado de infraestrutura: TRUNCATE preso em DataFileImmediateSync
Durante a validação, o mesmo `TRUNCATE` de fixture de teste (Postgres
rodando em Docker Desktop/WSL2, Windows) travou 3 vezes em
`wait_event = DataFileImmediateSync` por 30-50+ segundos sem contenção
de lock (`pg_locks` vazio) e CPU do processo Python praticamente parado
— não é deadlock de aplicação, é I/O de disco lento/instável no ambiente
virtualizado. Provável causa raiz do padrão de lentidão da suíte que
vem sendo observado nas últimas rodadas. Não investigado a fundo (fora
do escopo deste lote); registrado aqui como pista para quem for
investigar a lentidão da suíte depois.

### Arquivos criados
- `backend/app/services/pulse.py` (`build_pulse_snapshot`, extraído de
  `app/api/creator_interface.py::pulse()`).
- `backend/alembic/versions/0025_god_system_query.py` (permite
  `SYSTEM_QUERY` na CHECK constraint real do Postgres).

### Arquivos alterados
- `backend/app/core/god.py` (`SYSTEM_QUERY`, termos por tópico,
  `classify_system_query_topic`, formatação da resposta).
- `backend/app/services/god.py` (`_system_snapshot`, classificação
  prévia em `interact()`).
- `backend/app/repositories/god.py` (5 métodos de contagem, mínimos,
  só para SYSTEM_QUERY).
- `backend/app/models/god.py` (CheckConstraint do modelo SQLAlchemy
  atualizada para bater com a migration 0025).
- `backend/app/core/sophia.py` (`SYSTEM_QUERY_UNDERSTANDING`, corrige o
  `KeyError` latente).
- `backend/app/api/creator_interface.py` (`pulse()` agora chama
  `build_pulse_snapshot`, sem duplicar a lógica).
- `backend/tests/test_god.py`, `backend/tests/test_god_integration.py`,
  `backend/tests/test_sophia.py`
  (classificação dos 7 tópicos, não-regressão das outras 4 categorias,
  respostas refletindo dado real de banco, reuso comprovado do mesmo
  snapshot de Pulse).

## Investigação da lentidão da suíte de testes (2026-08-01)

### Causa raiz confirmada: fsync de disco, não configuração do Postgres nem estratégia de fixture

**H1 (bind mount para o filesystem do Windows) — descartada com evidência.**
`docker volume inspect thecreationos_postgres_data` mostra
`Mountpoint: /var/lib/docker/volumes/thecreationos_postgres_data/_data`
— um named volume nativo dentro da VM do WSL2 (`docker info` confirma
`Storage Driver: overlay2`, `Backing Filesystem: extfs`), não um bind
mount `/mnt/c/...`. Não é a causa.

**H2 (fsync desnecessário em ambiente de teste) — confirmada com
evidência direta e quantificada.** Um benchmark de fsync bruto dentro
do container `postgres` (mesma chamada de sistema que o WAL do
Postgres usa a cada commit/TRUNCATE):
```
dd if=/dev/zero of=fsync_test_file bs=8k count=200 oflag=dsync
```
levou **60.78s para 1.6MB (27 kB/s, ~300ms por write com fsync)** — um
disco íntegro faz isso em menos de 1-2s. Isso é lentidão de I/O de
disco virtualizado (Docker Desktop/WSL2 neste host Windows), não uma
escolha de configuração do Postgres em si — mas como o Postgres de
teste usava a mesma configuração seria de produção (`fsync=on`,
`synchronous_commit=on`, `full_page_writes=on`, todos padrão-seguros),
cada `TRUNCATE ... CASCADE` de fixture paga esse custo integralmente. É
a causa raiz consistente com os travamentos observados nos últimos 3
lotes (`TRUNCATE` preso em `wait_event=DataFileImmediateSync` por
30-50s+, `pg_locks` vazio — sem contenção de lock, I/O puro).

**H3 (TRUNCATE de todas as tabelas por teste) — real, mas não é a causa
raiz, é um amplificador.** Cada fixture já faz `TRUNCATE` só das
tabelas que usa (não das 43 tabelas do schema inteiro) — mas `CASCADE`
e o número de tabelas por fixture (até 15 na maior) multiplicam o
custo de cada fsync individual. Migrar para transação+ROLLBACK por
teste foi avaliado e descartado: vários testes fazem asserts via HTTP
(`AsyncClient`/`ASGITransport`) que abrem sua própria conexão via
`get_session` override, e outros (`test_worker_orchestration.py`,
`test_god_integration.py`) chamam `subprocess.run(alembic ...)` —
ambos exigem commit real cross-conexão, então ROLLBACK-por-teste
quebraria isolamento real que hoje é genuíno, não um mock escondendo
bug. Não implementado.

### Correção aplicada: serviço `postgres-test` isolado
Novo serviço em `docker-compose.yml`, **aditivo apenas** (`git diff
--stat`: 41 inserções, 0 remoções, nenhuma linha do serviço `postgres`
existente tocada):
```yaml
postgres-test:
  image: pgvector/pgvector:pg16
  command: ["postgres", "-c", "fsync=off", "-c", "synchronous_commit=off", "-c", "full_page_writes=off"]
  volumes: [postgres_test_data:/var/lib/postgresql/data]  # volume novo, não o postgres_data existente
  ports: ["5433:5432"]  # porta nova, não conflita com 5432
  profiles: [test]  # nunca sobe com `docker compose up` normal
```
Confirmado após a mudança: `docker compose exec postgres psql ... SHOW
fsync` continua `on` no serviço `postgres` de dev/produção — zero
impacto ali. Uso: apontar `TEST_DATABASE_URL` para
`localhost:5433/the_creation_os_test` em vez de `5432` ao rodar a
suíte localmente; subir com `docker compose --profile test up -d
postgres-test`.

### Medição real — antes e depois
Subconjunto representativo de 45 testes de integração (mesmo tamanho
de referência do "Lote 2.6: 40 testes/16m33s" citado no prompt):
`test_god_integration.py` + `test_sophia_integration.py` +
`test_rockmam_integration.py` + `test_trinity_integration.py` +
`test_worker_orchestration.py` + `test_dispatch_integration.py` +
`test_consolidation_integration.py`.

- **Antes** (`postgres` original, `fsync=on`): não foi possível obter
  uma medição única e limpa deste subconjunto exato — a mesma
  instabilidade de I/O sob investigação interrompeu 2 tentativas (`
  TRUNCATE` preso 30-50s+, processo morto e reiniciado). Em vez de
  forçar um número artificial, uso a medição limpa mais recente já
  registrada nesta sessão sob a mesma configuração não alterada:
  **23 testes de integração em 652.76s ≈ 28.4s/teste** (Lote Tree
  Core/Agentes/Malkuth, mesmo host, mesmo `postgres` original).
- **Depois** (`postgres-test`, `fsync=off`): **45/45 testes em 152.6s
  (2m32.6s) ≈ 3.39s/teste** — nenhum travamento em nenhuma das 4
  rodadas.
- **Aceleração: ~8.4× por teste.** Migration completa (0001→0025, 25
  revisões) caiu de operações que antes travavam individualmente por
  15-50s+ para **4.4s no total**.

### Confirmação de determinismo
4 rodadas consecutivas contra `postgres-test`, mesmo subconjunto de 45
testes: 152.6s, 146.8s, 132.6s, e uma 4ª rodada com saída completa
preservada (`.............................................  [100%]`,
45 pontos, zero `F`/`E`) — resultado idêntico (todos passando) nas 4,
nenhuma flutuação de pass/fail, só variação de tempo (132-153s) dentro
do esperado para um host compartilhado. As mensagens `ERROR` que
aparecem em `docker compose logs postgres-test` durante as rodadas
(`rockmam assessment is immutable`, `duplicate key ... uq_dispatch_active_task`,
etc.) são exatamente os `pytest.raises(...)` negativos que a própria
suíte testa de propósito — não falhas reais.

### Pendências reais
- A causa raiz de fundo (I/O de disco virtualizado lento no Docker
  Desktop/WSL2 deste host Windows) **não foi eliminada**, só contornada
  para testes — `fsync=off` é seguro apenas porque dados de teste são
  100% descartáveis (recriados do zero a cada `alembic upgrade head`
  session-scoped). O serviço `postgres` de dev/produção continua
  sujeito à mesma lentidão de disco se algum dia sob carga de escrita
  pesada; investigar isso é uma mudança de infraestrutura Windows/Docker
  Desktop (ex.: exclusão do Windows Defender para o disco virtual do
  WSL2, ou mover o Docker Desktop para outro disco), fora do escopo
  deste lote (que era sobre `docker-compose.yml`/fixtures de teste, não
  o SO host).
- Não obtive uma medição "antes" limpa do exato subconjunto de 45
  testes contra o `postgres` original (só um número comparável de 23
  testes) — documentado acima em vez de inventar um número.
- Uma medição da suíte completa (366 testes) não foi feita — o
  subconjunto de 45 testes de integração é representativo (mesma
  ordem de grandeza do "Lote 2.6" citado no prompt) e os ~245 testes
  não-integração já rodam em ~1-2s no total (não tocam Postgres), então
  a extrapolação linear é direta, mas não é uma medição real ponta-a-
  ponta da suíte inteira.

### Arquivos alterados
- `docker-compose.yml` (novo serviço `postgres-test` + novo volume
  `postgres_test_data`; nenhuma linha existente alterada).

## Lote: Convergência de memória de conversa (2026-08-01)

Decisão já tomada pelo Criador (não reaberta aqui): `conversation_memory`
passa a ser a fonte real que GOD consulta para contexto de memória;
`CreatorMemory` é depreciado nesse fluxo específico, não apagado.

### Auditoria — o que `CreatorMemory` fazia que `conversation_memory` não tinha
- **Seleção em duas etapas** (`app/core/memory.py`): `MemoryRepository.search()`
  filtra no banco por `creator_id` + `importance >= min_importance` +
  `memory_type IN (...)`, ordenado por `importance DESC, created_at DESC`,
  até 50 candidatos; depois `select_memory_context()` re-ranqueia em Python
  por `relevance_score = importance*10 + matches*4 + (3 se a query inteira
  aparece literalmente no conteúdo)`, onde `matches` é a contagem de termos
  da query (por espaço) que aparecem como substring no conteúdo
  normalizado; desempate por `(memory_type, source, id)`; corta nos 5
  primeiros. `conversation_memory` (`ScopedMemoryRepository.search()`) não
  tinha nada disso — só um `ILIKE` de substring sobre `key`/`value_json`
  inteiro, sem importância, sem tipo, sem pontuação de relevância.
- **Escopo Creator-wide, não por Conversation**: `CreatorMemory.creator_id`
  é direto — uma busca retorna memórias de todas as conversas do Criador.
  `ConversationMemory` é escopada por `conversation_id` (uma Conversation
  específica); `ScopedMemoryRepository` (Lote 2.5) foi desenhado
  deliberadamente de forma mono-escopo (um `parent_id` fixo por instância)
  — não serve para uma busca cross-conversation sem um método novo.
- **Ponto real de consulta em produção**: `GodConversationService._memory_context()`
  (`app/services/god.py`), chamado incondicionalmente em todo
  `interact()`, chamava `self.repository.memory.search(creator_id=actor.id,
  query=normalize_memory_text(message), memory_types=[...4 tipos...],
  min_importance=1, limit=50)` e depois `select_memory_context(candidates,
  query=message, limit=5)`. Note-se que `MemoryService.context_for_god()`
  (`app/services/memory.py`) já existia fazendo exatamente essa mesma
  lógica — mas GOD nunca a chamava, tinha a lógica reimplementada inline.
  Confirmado morto/nunca usado por GOD; deixado como está (deprecated, não
  apagado).
- **Outro consumidor real de CreatorMemory além de GOD** (a auditoria
  pedia explicitamente para não presumir que só GOD usa isso — e havia,
  de fato): `app/api/memory.py` expõe `POST /memory` e
  `GET /memory/search`, uma API HTTP standalone, ativa e independente do
  fluxo de GOD, que grava/lê `CreatorMemory` diretamente. Ver pendência
  crítica abaixo.

### Escopo de leitura resolvido: join Creator-wide sobre conversation_memory
Novo método `GodConversationRepository.conversation_memory_candidates()`
(`app/repositories/god.py`) — `JOIN Conversation ON Conversation.id ==
ConversationMemory.conversation_id WHERE Conversation.creator_id ==
:creator_id AND (value_json->>'importance')::int >= :min_importance
[AND value_json->>'memory_type' IN (...)]`, ordenado por
`importance DESC, created_at DESC`, `LIMIT :limit` — mesmo filtro/ordem
que `MemoryRepository.search()` fazia, agora atravessando todas as
Conversations do Criador em vez de uma tabela própria. Sintaxe SQLAlchemy
testada diretamente contra o Postgres real antes de escrever
(`ConversationMemory.value_json["importance"].as_integer()` compila para
`CAST(value_json ->> 'importance' AS INTEGER)`).

Cada linha retorna um `ConversationMemoryCandidate` (dataclass nova,
`app/repositories/god.py`) que espelha exatamente os atributos que
`select_memory_context()` já esperava de uma linha de `CreatorMemory`
(`id, memory_type, source, content, importance, normalized_content,
memory_fingerprint`) — **`select_memory_context()` em si não foi tocado**,
reaproveitado 100% sem mudança.

### Formato escolhido dentro de `value_json` (decisão de gosto, seção 7)
`ConversationMemory.key = memory_fingerprint` (64 chars hex, cabe no
`String(128)` da coluna); `value_json = {"memory_type", "source",
"content", "normalized_content", "importance", "memory_fingerprint"}` —
espelha os campos de `CreatorMemory` 1:1, opção mais simples e mais
próxima do que já existia, sem migration de schema (a tabela já suporta
JSON livre). Chave = fingerprint em vez de um nome arbitrário reaproveita
a mesma semântica de dedupe por conteúdo que `CreatorMemory.remember()`
já tinha via `by_fingerprint()`.

### `GodConversationService._memory_context()` — trecho real
```python
async def _memory_context(self, actor: Actor, message: str) -> list[dict]:
    candidates = await self.repository.conversation_memory_candidates(
        actor.id,
        memory_types=[item.value for item in MemoryType],
        min_importance=1,
        limit=50,
    )
    return [... select_memory_context(candidates, query=message, limit=5) ...]
```

### Migração de dados — auditada, nenhum dado real encontrado
```sql
-- banco de dev persistente (the_creation_os), não o de teste
SELECT count(*) FROM creator_memories;  -- 0
SELECT count(*) FROM conversation_memory;  -- 0
SELECT count(*) FROM conversations;  -- 5 (existem Conversations reais, mas nenhuma memória)
```
Zero registros em `creator_memories` no ambiente real disponível — por
instrução explícita da seção 3b, a migração de dados foi **pulada, não
escrita**, em vez de construir e manter código ETL não testável contra
dado real algum. Convenção documentada para se este cenário aparecer no
futuro (ex.: outro ambiente com dado real): mapear cada `CreatorMemory`
para uma linha de `ConversationMemory` presa à Conversation mais antiga
do mesmo `creator_id` (já que `CreatorMemory` nunca teve vínculo com
Conversation nenhuma — é uma perda de informação inerente e inevitável
de qualquer mapeamento), preservando `created_at` e usando o mesmo
`value_json`/`key=fingerprint` acima. Nenhuma migration de schema foi
necessária (`conversation_memory` já existe desde `0001_initial`, campo
`value_json` já é livre).

### Pendência crítica: `POST /memory` continua escrevendo onde GOD não lê mais
Este é o achado mais importante desta auditoria. `app/api/memory.py`
(`POST /memory`, `GET /memory/search`) é uma rota HTTP real, ativa, fora
do fluxo de GOD — **não foi alterada** (fora do escopo autorizado: "não
altere nenhum outro fluxo de GOD além da resolução de memória", e essa
rota nem é fluxo de GOD). Consequência real e imediata: qualquer memória
nova criada via essa rota grava em `CreatorMemory`, que GOD não lê mais
— fica invisível para o contexto de conversa a partir de agora. Como não
havia dado real a migrar, o efeito prático imediato neste ambiente é que
o contexto de memória de GOD começa vazio (comportamento correto e
íntegro, só sem histórico ainda) até que exista um caminho de escrita
real para `conversation_memory`, que este lote não constrói (não foi
pedido, e construir um por conta própria seria expandir escopo sem
autorização). Marcado com comentário explícito em `app/api/memory.py` e
aqui. Fica para o Criador decidir, em um lote futuro, entre: (a)
grava duplo — `POST /memory` passa a escrever também em
`conversation_memory`; (b) uma rota nova, dedicada, escrevendo só em
`conversation_memory`, aposentando `POST /memory` de vez.

### Depreciação confirmada, não apagada
- `app/models/memory.py::CreatorMemory` — docstring de depreciação.
- `app/repositories/memory.py::MemoryRepository` — docstring de depreciação.
- `app/services/memory.py::MemoryService` — docstring de depreciação só em
  `context_for_god` (nunca foi chamado por GOD); `remember`/`search`
  continuam ativos e não depreciados (seguem servindo `POST/GET /memory`).
- `app/api/memory.py` — rota não depreciada nem alterada, só comentada com
  o aviso da pendência acima.
- Tabela `creator_memories` e todo o código: intactos, nada apagado.

### Achado colateral (fora de escopo, documentado): migration `0023_universe_agent_seed` quebra ao retomar de estado intermediário
Descoberto ao rodar a suíte de regressão contra `postgres-test`: se um
teste de round-trip de migration (`test_0014_migration_round_trip_...`,
`test_0015_...`) deixa o banco numa revisão intermediária (comportamento
intencional desses testes) e uma invocação de `pytest` subsequente tenta
`alembic upgrade head` a partir dali, `0023_universe_agent_seed` falha
com `ForeignKeyViolationError` (`agents.universe_id` referenciando um
`universes.id` que ainda não existe nesse ponto do encadeamento). Rodando
do zero (`alembic upgrade head` a partir de banco vazio) sempre funciona
— confirmado. É um bug real e pré-existente na migration 0023 (não
causado por este lote nem pelo `postgres-test`), só nunca exposto antes
porque nada rodava `alembic upgrade head` a partir de um estado
intermediário fora desses testes de round-trip isolados. Registrado como
gotcha operacional em `docs/testing.md` (resetar `postgres-test` se isso
acontecer); correção da migration em si fica para um lote futuro
dedicado — fora do escopo de convergência de memória.

### Testes
- `tests/test_god.py`: `FakeGodRepository` trocou `.memory.search(...)`
  (CreatorMemory) por `.conversation_memory_candidates(...)` — mesmo
  comportamento observável validado (13/13 passam).
- `tests/test_god_integration.py`: teste novo,
  `test_memory_context_reads_conversation_memory_creator_wide_not_creator_memory`
  — prova as duas propriedades que precisavam sobreviver à migração:
  recall Creator-wide (memória semeada numa Conversation *diferente* da
  usada na interação, e ainda assim encontrada) e extração correta de
  `content`/`importance`/`fingerprint` de dentro do `value_json`. Não
  existia nenhum teste de integração real (banco de verdade) para
  `_memory_context` antes deste lote — só o unit test com fake.
- `tests/test_memory.py`, `tests/test_scoped_memory.py`: inalterados,
  continuam validando `CreatorMemory`/`conversation_memory` nos seus
  próprios contratos, sem depender do que mudou aqui.

### Arquivos criados
Nenhum.

### Arquivos alterados
- `backend/app/repositories/god.py` (`ConversationMemoryCandidate`,
  `conversation_memory_candidates()`).
- `backend/app/services/god.py` (`_memory_context` aponta para
  `conversation_memory`; import de `normalize_memory_text` removido, não
  usado mais aqui).
- `backend/app/models/memory.py`, `backend/app/repositories/memory.py`,
  `backend/app/services/memory.py` (docstrings de depreciação, zero
  mudança de comportamento).
- `backend/app/api/memory.py` (comentário sobre a pendência, zero mudança
  de comportamento).
- `backend/tests/test_god.py`, `backend/tests/test_god_integration.py`.

## Lote: Fechar gap de POST /memory + corrigir bug de migration 0023 (2026-08-01)

Duas partes independentes, reportadas separadamente.

### PARTE A — POST /memory agora escreve em conversation_memory

**Mismatch de escopo, decisão tomada**: `conversation_memory` é
estritamente escopada por `conversation_id`; `POST /memory` sempre foi
Creator-wide, sem conversa associada. Resolvido com uma **Conversation
âncora** por Criador — mesmo padrão que `app/services/opportunities.py`
já usa para sua própria Conversation sintética ("Opportunity
Discovery"). `CreatorRecallRepository.anchor_conversation_id(creator_id)`
(`app/repositories/creator_recall.py`, novo) resolve ou cria (idempotente,
`title="__creator_memory__"`) essa Conversation dedicada; toda memória
gravada por `POST /memory` é anexada a ela. Nenhuma mudança de schema em
`conversation_memory` — a tabela já existe, `value_json` já é livre.
`GodConversationRepository.conversation_memory_candidates()` (do lote
anterior, inalterado) já faz um `JOIN` Creator-wide sobre `Conversation`,
então passa a enxergar essas memórias automaticamente, sem nenhuma
mudança nele.

Decisão de escala pequena e aceitável dentro do permitido pela seção 2:
nenhuma coluna nova, nenhuma migration de schema — só uma linha de
`Conversation` sintética por Criador, criada sob demanda.

Novo `CreatorRecallService` (`app/services/creator_recall.py`) — mesma
interface pública que `MemoryService` tinha (`remember`/`search`),
mesmas validações (`importance` 1–10, `content`/`source` não vazios),
mesmo `build_memory_document()`/dedupe por fingerprint (reaproveitado de
`app/core/memory.py`, inalterado) — só troca o destino de escrita/leitura
para `ScopedMemoryRepository`/`ScopedMemoryService` (Lote 2.5,
inalterados) apontando para a Conversation âncora. `app/api/memory.py`
agora injeta `CreatorRecallService`/`CreatorRecallRepository` em vez de
`MemoryService`/`MemoryRepository`. `memory_response()` não mudou de
assinatura observável — `RememberedMemory` (novo dataclass) espelha
exatamente os mesmos atributos que uma linha de `CreatorMemory` tinha,
então o schema de resposta HTTP (`MemoryResponse`) é 100% idêntico.

```python
# app/services/creator_recall.py — trecho real
document = build_memory_document(
    creator_id=actor.id, memory_type=memory_type, content=content,
    source=source, importance=importance, metadata=metadata,
)
anchor_id = await self.repository.anchor_conversation_id(actor.id)
scoped_repository = ScopedMemoryRepository(self.repository.session, ConversationMemory, "conversation_id", anchor_id)
existing = await scoped_repository.get_by_key(document.fingerprint)
created = existing is None
scoped_service = ScopedMemoryService(scoped_repository, aggregate_type="creator_memory", actor_id=actor.id, actor_role=actor.role)
item = await scoped_service.set(document.fingerprint, value_json, correlation_id=correlation_id)
```

**Confirmado que GOD lê o que `POST /memory` escreve** — prova real,
ponta a ponta, sem seed manual de banco:
`test_god_memory_context_reflects_what_post_memory_wrote_end_to_end`
(`tests/test_memory_integration.py`) — `POST /memory` via HTTP real, depois
`GodConversationService.interact()`, confirma que o conteúdo aparece no
`memory_context` de fato usado.

`CreatorMemory`/`MemoryRepository`/`MemoryService` continuam depreciados
(docstrings do lote anterior), agora **genuinamente sem nenhuma chamada
ativa** em todo o sistema — o gap está fechado.

#### Testes — Parte A
`tests/test_memory_integration.py` (novo, 4 testes reais contra Postgres:
escreve em `conversation_memory` não `CreatorMemory`; idempotência por
fingerprint; `GET /memory/search` lê o que foi escrito; GOD reflete o
que `POST /memory` escreveu). `tests/test_memory.py` (existente,
inalterado — continua validando o contrato próprio, ainda válido, de
`MemoryService`/a forma HTTP via fakes; nenhuma perda de cobertura).
Regressão de GOD (`test_god.py`, `test_god_integration.py`) sem
mudança, sem regressão.

#### Arquivos — Parte A
Criados: `backend/app/repositories/creator_recall.py`,
`backend/app/services/creator_recall.py`,
`backend/tests/test_memory_integration.py`.
Alterados: `backend/app/api/memory.py`.

### PARTE B — Bug de `0023_universe_agent_seed` corrigido

**Causa raiz exata** (confirmada por reprodução real, não suposição):
os 4 `INSERT` de `0023_universe_agent_seed.upgrade()` usavam
`ON CONFLICT DO NOTHING` **sem qualificar a coluna** — isso casa com
conflito em **qualquer** constraint UNIQUE da tabela, não só a PK.
`universes.code` e `capabilities.name` têm UNIQUE próprio. Se uma linha
com o mesmo `code`/`name` já existir sob um **id diferente** (ex.: uma
fixture de teste inserindo `Universe(id=uuid4(), code="knowledge", ...)`
diretamente, sem passar pelos ids estáticos canônicos desta migration),
o insert da linha canônica silenciosamente vira no-op — o id canônico
nunca é criado — e o insert de `agents` dois loops depois, cuja FK
`universe_id` referencia esse id agora ausente, falha com
`ForeignKeyViolationError`, um erro confuso e distante da causa real.

Reproduzido isoladamente, ANTES de escrever a correção:
```
alembic upgrade head   (de banco vazio — OK)
alembic downgrade 0022_pgvector_extension
alembic upgrade head   (round trip puro, SEM nenhuma fixture de teste) — sucesso!
```
Round trip puro **não** reproduz o bug — só reproduz quando algo fora do
framework de migration já inseriu uma linha conflitante:
```
alembic downgrade 0022_pgvector_extension
INSERT INTO universes (id, code, ...) VALUES ('99999999-...', 'knowledge', ...)
alembic upgrade head
→ ForeignKeyViolationError: agents_universe_id_fkey (o erro confuso, distante da causa real)
```

**Decisão: corrigida em `0023` mesma, não em migration nova.** A
migration já está aplicada no banco persistente real
(`alembic_version` confirmado adiante de `0023` no ambiente de dev) —
mas diferente do caso do `SYSTEM_QUERY` (que exigia uma nova migration
porque a correção era uma mudança de *constraint* já vigente no schema
real), aqui a correção é só robustez da lógica de `upgrade()`: para
qualquer ambiente que já rodou `0023` sem contaminação (o caso normal,
sempre), o estado final produzido é **idêntico** antes e depois — a
mudança só afeta o comportamento do caso anômalo (conflito de
código/nome sob id diferente). E é estruturalmente impossível corrigir
via migration nova: o bug está na lógica do `upgrade()` de `0023`
propriamente dito — nenhuma migration posterior na cadeia pode mudar o
que `0023` faz quando ELA roda.

```sql
-- antes
INSERT INTO universes (id, code, name, active) VALUES (...) ON CONFLICT DO NOTHING
-- depois
INSERT INTO universes (id, code, name, active) VALUES (...) ON CONFLICT (id) DO NOTHING
```
(mesma correção para `capabilities`, `agents`; `agent_capabilities` ganhou
`ON CONFLICT (agent_id, capability_id) DO NOTHING` explícito, já era a
única constraint ali mas agora está expresso).

**Efeito real da correção**: o caso normal (sem contaminação) continua
idêntico. O caso anômalo (contaminação por código/nome já existente sob
outro id) agora falha **imediatamente e claramente**
(`UniqueViolationError` em `universes_code_key`, no primeiro insert) em
vez de falhar de forma confusa e tardia (`ForeignKeyViolationError` em
`agents_universe_id_fkey`, dois loops depois). Isso **não** faz o caso
contaminado "funcionar" — dado genuinamente conflitante deve mesmo
falhar; só melhora a clareza/imediatismo do erro.

#### Testes — Parte B
`tests/test_migration_0023_seed_idempotency.py` (novo, 2 testes):
`test_0023_pure_round_trip_from_intermediate_revision_succeeds` (o
cenário original do bug report — resumir `upgrade head` após downgrade
abaixo de 0023 — regressão-guard, sempre funcionou e continua
funcionando); `test_0023_conflicting_row_under_different_id_now_fails_loudly_not_confusingly`
(prova a correção real: contaminação agora falha imediatamente citando
`universes_code_key`, nunca mais `agents_universe_id_fkey`). Ambos
passam contra `postgres-test` (22.13s) **e** contra o `postgres`
original sem modificação (25.43s) — confirmando equivalência, conforme
exigido pela validação geral do lote.

#### Arquivos — Parte B
Alterado: `backend/alembic/versions/0023_universe_agent_seed.py`
(qualificação explícita dos `ON CONFLICT`, docstring da correção).
Criado: `backend/tests/test_migration_0023_seed_idempotency.py`.

### Pendências reais
- Parte A: nenhuma pendência conhecida — o gap do lote anterior está
  fechado, GOD lê o que `POST /memory` escreve, ponta a ponta, com
  prova real.
- Parte B: nenhuma pendência — causa raiz identificada com reprodução
  real, corrigida, testada em `postgres-test` e no `postgres` original.
  Observação não-crítica: a Conversation âncora (`__creator_memory__`,
  Parte A) e o teste de contaminação da Parte B ambos inserem linhas
  fora do "seed canônico" da própria migration — nenhuma delas colide
  com `code`/`name` reservados por `0023`, então não há risco cruzado
  entre as duas partes deste lote.

## Lote: Busca ANN real via pgvector (2026-08-01)

### Auditoria — confirmado antes de mexer em código
- **Coluna `embedding`**: confirmado com `\d conscious_memory` que era
  `real[]` (`postgresql.ARRAY(postgresql.REAL())`), não o tipo `vector`
  nativo — exatamente a suspeita do prompt. A extensão `vector` já
  estava habilitada (`0022_pgvector_extension`), mas nunca ligada a uma
  coluna de verdade.
- **Versão do pgvector instalada**: `SELECT extversion FROM
  pg_extension WHERE extname='vector'` → **0.8.5** (Postgres 16.14,
  imagem `pgvector/pgvector:pg16`) — HNSW suportado e estável desde
  0.5.0, então disponível sem downgrade de versão.
- **Dado real a migrar**: `SELECT count(*) FROM conscious_memory` no
  banco de dev persistente → **0 registros**. Sem ETL — só migration de
  schema, conforme instrução 3.
- **pacote `pgvector-python`**: não era dependência ainda. Decisão de
  gosto (seção 7): adicionado como dependência nova (`pgvector>=0.3.0`
  em `pyproject.toml`) em vez de operadores SQL crus — o tipo
  `pgvector.sqlalchemy.Vector` faz o (de)serialização
  Python-list↔`vector` corretamente através do SQLAlchemy/asyncpg sem
  precisar de `numpy` (não instalado; o pacote cai para `list` puro
  quando `numpy` está ausente) nem de parsing manual de literal
  `'[1,2,3]'::vector` espalhado pelo código. Avaliado como mais simples
  de manter do que a alternativa crua, apesar de ser uma dependência
  nova — não uma leitura literal de "só use se já for dependência", mas
  a opção que produz menos código frágil.

### Índice: HNSW, não IVFFlat — com justificativa
IVFFlat exige um parâmetro `lists` calibrado ao volume esperado de
linhas (tipicamente `sqrt(n)`) e degrada se o índice for criado antes
da tabela ter dados reais (k-means de clustering roda uma vez, no
`CREATE INDEX`). HNSW não precisa desse parâmetro, constrói
incrementalmente, e é a opção hoje recomendada pelo próprio pgvector
para a maioria dos casos — na versão 0.8.5 instalada, madura desde
0.5.0. Escolhido `vector_cosine_ops` (distância de cosseno) porque é
exatamente a métrica que `cosine_similarity()` (removida) já usava.
Parâmetros de build default (`m=16, ef_construction=64`) — adequados
para a escala de milhares de linhas esperada; calibração fina fica
como pendência real se o volume em produção crescer muito além disso.

### Migration `0026_conscious_memory_vector`
```sql
ALTER TABLE conscious_memory ALTER COLUMN embedding TYPE vector(8) USING embedding::vector(8);
CREATE INDEX ix_conscious_memory_embedding_hnsw ON conscious_memory USING hnsw (embedding vector_cosine_ops);
```
`real[]::vector(N)` é um cast nativo do pgvector (confirmado por
consulta direta antes de escrever a migration). Dimensão 8 hardcoded,
igual ao default de `settings.conscious_memory_embedding_dim` — **atenção**:
diferente de `real[]`/JSON, a dimensão de `vector(N)` é fixa na própria
coluna; mudar `CONSCIOUS_MEMORY_EMBEDDING_DIM` no futuro exige uma
migration nova alterando essa dimensão também. Documentado como
limitação real e inerente do pgvector, não uma lacuna evitável.

### Busca — antes/depois
```python
# antes (app/repositories/conscious_memory.py)
async def search_by_embedding(self, embedding, *, limit):
    candidates = await self.all_candidates()  # até 500, sempre
    ranked = sorted(candidates, key=lambda item: cosine_similarity(embedding, list(item.embedding)), reverse=True)
    return ranked[:limit]

# depois
async def search_by_embedding(self, embedding, *, limit):
    stmt = select(ConsciousMemory).order_by(ConsciousMemory.embedding.cosine_distance(embedding)).limit(limit)
    result = await self.session.scalars(stmt)
    return list(result.all())
```
Interface pública do `MemoryStore` (`ConsciousMemoryService.search()`)
**inalterada** — só a implementação interna mudou. `all_candidates()`
continua existindo, usado só para o caminho "sem query" (listar mais
recentes), não relacionado à mudança de ANN.

### Medição real (2000 linhas, bem acima do limite de 500 candidatos anterior)
- **Confirmado via `EXPLAIN`** que o índice é de fato usado — precisa
  de `ANALYZE conscious_memory` após um bulk insert (estatísticas
  frescas); sem isso, o planner subestima a tabela e escolhe `Seq Scan`
  mesmo com o índice presente — comportamento real do Postgres,
  documentado no teste, não uma suposição:
  ```
  Index Scan using ix_conscious_memory_embedding_hnsw on conscious_memory
  ```
- **pgvector (HNSW, LIMIT 5)**: 3.6ms/chamada.
- **Antes (Python, fetch de até 500 + ranking em Python)**: 24.9ms/chamada.
- **Aceleração real medida: ~6.9×** (`tests/test_conscious_memory_ann_performance.py`,
  10 chamadas cada, média).

### Achado colateral (não corrigido, fora de escopo): flakiness de suíte completa por ordem de teste
Rodar `test_god_integration.py` inteiro (17 testes) às vezes falha em
cascata com `CheckViolationError` em `ck_god_interaction_type`, mas
**cada teste envolvido passa perfeitamente quando rodado sozinho**
(confirmado: `test_0013_migration_round_trip_constraints_and_triggers`
isolado, com a migration 0026 no encadeamento, passa limpo). Não é bug
de `conscious_memory`/pgvector — nenhum teste deste lote toca
`god_conversation_interactions`. É uma fragilidade pré-existente de
ordenação/isolamento entre testes no arquivo, exposta mas não causada
por este lote. Fora de escopo corrigir aqui; registrado como pendência
real para investigação futura, se o Criador priorizar.

### Testes
`tests/test_conscious_memory.py` (existente, `cosine_similarity` e seu
teste unitário removidos — a função não existe mais, o ranking é 100%
no Postgres agora — os outros 4 testes de comportamento continuam
validando o mesmo contrato observável). `tests/test_conscious_memory_ann_performance.py`
(novo): índice realmente usado (EXPLAIN), vizinho mais próximo correto
em 2000 linhas, medição real de performance antes/depois.
`tests/test_conscious_memory_consolidation_triggers.py`,
`tests/test_knowledge_memory_integration.py` — sem alteração, sem
regressão (confirmados isoladamente e via o subconjunto principal:
23/23 em `test_conscious_memory*.py` + `test_god.py`).

### Validação
`ruff check`: limpo. Migration aplicada e verificada (`\d conscious_memory`
mostrando `vector(8)` + índice HNSW) tanto em `postgres-test` quanto no
`postgres` original. Testes principais: 23/23 (`postgres-test`, 23s) e
10/10 (`postgres` original, contra os mesmos arquivos de
`conscious_memory`, ~98s — consistente com a proporção de velocidade já
documentada entre os dois serviços).

### Arquivos criados
- `backend/alembic/versions/0026_conscious_memory_vector.py`
- `backend/tests/test_conscious_memory_ann_performance.py`

### Arquivos alterados
- `backend/pyproject.toml` (dependência nova: `pgvector`).
- `backend/app/models/entities.py` (`embedding` agora `Vector(8)`, não
  `postgresql.ARRAY(postgresql.REAL())`; import `postgresql` removido,
  ficou sem uso).
- `backend/app/repositories/conscious_memory.py` (`search_by_embedding`
  reescrito para usar `cosine_distance()` nativo; `cosine_similarity()`
  removida).
- `backend/tests/test_conscious_memory.py` (import e teste de
  `cosine_similarity` removidos).

### Pendências reais
- Calibração fina dos parâmetros HNSW (`m`, `ef_construction`,
  `ef_search`) para volume real de produção — os defaults do pgvector
  foram usados, adequados para a escala atual (milhares de linhas), mas
  não testados/calibrados para uma escala muito maior.
- Mudar `CONSCIOUS_MEMORY_EMBEDDING_DIM` no futuro exige uma migration
  nova para alterar a dimensão da coluna `vector(N)` — documentado
  acima, não implementado preventivamente (não foi pedido).
- Flakiness de ordenação de teste em `test_god_integration.py` rodado
  por inteiro (achado colateral acima) — não é deste lote, mas seria
  bom investigar/corrigir num lote futuro dedicado a robustez de
  suíte.
- Imagem Docker do `api`/`worker` ainda não foi reconstruída com a
  nova dependência `pgvector` — necessário `docker compose build api
  worker` antes de um deploy real; a validação deste lote rodou via
  pytest direto no host contra Postgres real, não através dos
  containers da aplicação.

## Lote: Investigação de fragilidade de ordenação em test_god_integration.py (2026-08-01)

### Causa raiz confirmada — duas manifestações do mesmo padrão (H1: fixture não isolada)
Combinação mínima reproduzida: **`test_knowledge_memory_integration.py` seguido
de `test_god_integration.py`**, nessa ordem — `test_god_integration.py`
sozinho, rodado 5x+ seguidas, **nunca falhou**.

`test_knowledge_memory_integration.py`'s `knowledge_memory_db` TRUNCATE +
reseeda `capabilities`/`agents`/`universes` com ids sintéticos aleatórios
(padrão legítimo, usado por vários arquivos de teste) — confirmado por
consulta direta: depois desse teste, `capabilities` tem exatamente 1 linha,
`name='knowledge_research'`, id aleatório (não o id estático canônico
`20000000-...0001` de `0023_universe_agent_seed`). Isso alimenta dois
efeitos reais, ambos capturados com stack trace completo antes da correção:

- **(a) Recovery da migration falha**: quando `test_0013_migration_round_trip_...`
  roda depois, seu teardown (`pytest_runtest_teardown` em `conftest.py`)
  reaplica `alembic upgrade head`, que tenta reinserir a `capability`
  canônica — `UniqueViolationError` em `capabilities_name_key` (correto e
  alto, graças ao fix do lote anterior de `0023`), fazendo o subprocess de
  recovery falhar e deixar o banco preso abaixo da migration `0025` (sem a
  CHECK constraint que permite `SYSTEM_QUERY`) para todos os testes
  seguintes na mesma sessão.
- **(b) O próprio downgrade do teste de round-trip falha**: se outro teste
  anterior (ex.: `test_service_interaction_types[...SYSTEM_QUERY...]`,
  já dentro do próprio `test_god_integration.py`) já gravou uma linha real
  com `interaction_type='SYSTEM_QUERY'` em `god_conversation_interactions`,
  o downgrade de `0025_god_system_query` (que recria a CHECK constraint
  antiga, sem `SYSTEM_QUERY`) falha com `CheckViolationError` **dentro do
  próprio corpo do teste**, antes de qualquer teardown — capturado com
  stack trace completo apontando exatamente para
  `0025_god_system_query.py::downgrade()`.

Não é H2 (sem estado de processo/singleton envolvido), H3 (não é sobre
ordem de criação/timestamp) nem H4 (sem race condition assíncrona — é
100% sobre dado real persistido no Postgres compartilhado entre testes).

### Correção — não mitigação: elimina a colisão na origem, não esconde o sintoma
`tests/conftest.py` ganhou dois hooks simétricos, num único ponto de
convergência (em vez de corrigir cada fixture/teste de round-trip
individualmente):
```python
_MIGRATION_SEED_TABLES = "agent_capabilities, agents, capabilities, universes"
_EVOLVING_CONSTRAINT_TABLES = "god_conversation_interactions, sophia_understandings, rockmam_possibility_assessments"
_ROUND_TRIP_GUARD_TABLES = f"{_MIGRATION_SEED_TABLES}, {_EVOLVING_CONSTRAINT_TABLES}"

def pytest_runtest_setup(item):      # NOVO — protege (b): antes do teste
    if "migration_round_trip" not in item.name:
        return
    ...
    _clear_round_trip_guard_tables(test_database_url)

def pytest_runtest_teardown(item, nextitem):  # já existia — agora também limpa antes do upgrade head, protege (a)
    if "migration_round_trip" not in item.name:
        return
    ...
    _restore_to_head(test_database_url)  # chama _clear_round_trip_guard_tables() antes do "alembic upgrade head"
```
Isso garante que qualquer teste "migration round trip" sempre encontra as
tabelas de seed/constraint-evolutiva vazias antes de downgradar OU antes
de reaplicar `upgrade head` — independente do que qualquer outro teste
tenha deixado para trás. Nenhum `sleep`, `skip`, `xfail` ou timeout
maior — a causa real (colisão de dado entre testes que compartilham o
mesmo Postgres) foi eliminada no ponto de convergência, não escondida.

### Taxa de sucesso real após a correção
- Combinação mínima (`test_knowledge_memory_integration.py` +
  `test_god_integration.py`), sequencial: **10/10 rodadas limpas**
  (`postgres-test`).
- Mesma combinação + `test_sophia_integration.py` +
  `test_rockmam_integration.py` (as duas outras tabelas
  `_EVOLVING_CONSTRAINT_TABLES` protege), com **ordem aleatória**
  (`pytest-randomly`): **3/3 rodadas limpas**.
- Conjunto mais amplo (`test_conscious_memory*.py` +
  `test_knowledge_memory_integration.py` + `test_god.py` +
  `test_god_integration.py`), com ordem aleatória: **3/3 rodadas
  limpas**.
- Confirmado 1x contra o `postgres` original (não só `postgres-test`):
  limpo, 2m51s.
- `ruff check`: limpo.

### `pytest-randomly` — decisão: manter como dependência de teste permanente
Instalado só para diagnóstico inicialmente; decisão registrada: **manter**
(`pyproject.toml`, `dev` extras). Motivo: já provou valor real nesta
investigação (confirmou que a correção não depende de uma ordem
específica favorável) e, ativo por padrão em toda execução futura da
suíte, pega esta exata classe de bug — dependência oculta de ordem entre
testes que compartilham o mesmo Postgres — automaticamente, sem precisar
de um lote de investigação dedicado cada vez que aparecer de novo.

### Arquivos alterados
- `backend/tests/conftest.py` (dois hooks, `_ROUND_TRIP_GUARD_TABLES`).
- `backend/pyproject.toml` (`pytest-randomly` adicionado aos `dev` extras).

### Pendências reais
- `pytest-randomly` agora ativo por padrão pode revelar OUTRAS
  dependências de ordem pré-existentes em algum lugar dos ~366 testes da
  suíte completa, ainda não auditadas — fora do escopo deste lote (que
  investigou especificamente o padrão relatado em
  `test_god_integration.py`), mas uma consequência esperada e desejada
  de mantê-lo ativo; qualquer nova falha revelada deve ser tratada pelo
  mesmo princípio usado aqui (causa raiz real, não silenciamento).
- `_EVOLVING_CONSTRAINT_TABLES` cobre as 3 tabelas conhecidas hoje
  (`god_conversation_interactions`, `sophia_understandings`,
  `rockmam_possibility_assessments`) — se uma migration futura adicionar
  uma CHECK constraint nova a outra tabela com o mesmo padrão de
  evolução, essa tabela precisa ser adicionada à lista manualmente; não
  há verificação automática que force isso.

## Lote: Confirmar rebuild do Docker — pgvector-python (2026-08-01)

`docker compose build api worker` real: sucesso, `pgvector-0.5.0`
instalado em ambas as imagens (confirmado no log de build:
`Successfully installed ... pgvector-0.5.0 ...`).

**Bug real encontrado durante a verificação, não presumido**: depois do
rebuild, `docker compose up -d` deixou `api` em `unhealthy` e `worker`
nunca chegou a iniciar (`depends_on: api: condition: service_healthy`).
Causa: `EXPECTED_ALEMBIC_REVISION = "0024_creator_singleton"`
hardcoded em `app/api/health.py`, nunca atualizada pelos lotes
`SYSTEM_QUERY` (migration 0025) nem `pgvector`/ANN (migration 0026) —
`/api/v1/health/ready` comparava a revisão real (`0026_...`, já
corretamente aplicada pelo próprio `CMD` de startup do container) contra
o valor antigo e retornava 503 sempre. Zero cobertura de teste sobre
essa constante (`grep` confirma nenhum teste referencia
`EXPECTED_ALEMBIC_REVISION` nem `/health/ready`), por isso passou
despercebido em 2 lotes anteriores — só a auditoria de docs já tinha
notado a menção desatualizada no README (linha 128), não a constante de
código que efetivamente bloqueia o serviço. Corrigido:
`EXPECTED_ALEMBIC_REVISION = "0026_conscious_memory_vector"`.
Api reconstruída de novo com a correção; confirmado saudável.

### Confirmações finais (banco `the_creation_os`, real, não `_test`)
- `pgvector` importável no container `api`: `pgvector.sqlalchemy.Vector`
  resolvido, `importlib.metadata.version('pgvector')` = `0.5.0`.
- `alembic_version` = `0026_conscious_memory_vector`.
- `conscious_memory.embedding` = `vector(8)`, índice
  `ix_conscious_memory_embedding_hnsw` (hnsw, `vector_cosine_ops`)
  presente.
- `ck_god_interaction_type` já inclui `SYSTEM_QUERY`.
- `docker compose ps`: **6/6 serviços saudáveis** (`api`, `worker`,
  `frontend`, `postgres`, `postgres-test`, `redis`).

### Arquivos alterados
- `backend/app/api/health.py` (`EXPECTED_ALEMBIC_REVISION` atualizada).

### Pendências reais
- `README.md` linha ~128 continua com o texto desatualizado
  (`0024_creator_singleton`) mencionado na auditoria de documentação
  anterior — a CORREÇÃO FUNCIONAL já foi feita aqui (no código real que
  bloqueava o serviço); só o texto do README ainda precisa do ajuste
  cosmético equivalente, num lote de documentação.
- Nenhum teste cobre `/health/ready`/`EXPECTED_ALEMBIC_REVISION` — essa
  classe de regressão (constante esquecida ao adicionar uma migration
  nova) pode voltar a acontecer na próxima migration; vale um teste
  dedicado num lote futuro.

## Lote: Health check com revisão Alembic dinâmica (2026-08-01)

Elimina a causa raiz do bug do lote anterior, não só o sintoma: a
constante `EXPECTED_ALEMBIC_REVISION` foi removida por completo de
`app/api/health.py` (`grep` confirma zero ocorrências no repositório
fora do próprio texto histórico deste arquivo). `/health/ready` agora
resolve a head real chamando
`ScriptDirectory.from_config(config).get_current_head()` sobre
`alembic/versions/` a cada checagem — a mesma fonte de verdade que
`alembic upgrade head` usa — em vez de uma string lembrada manualmente
a cada migration nova. Resolução deliberadamente não cacheada: o custo
de reler alguns arquivos pequenos é desprezível, e cachear introduziria
de volta o mesmo problema de invalidação manual que esta mudança
existe para eliminar. Falha na resolução (ex.: diretório de migrations
inacessível) é capturada num `try/except` próprio, com `detail`
distinto do erro genérico de banco/redis, para não confundir as duas
causas num 503 igual.

### Testes reais (`backend/tests/test_health.py`, novo arquivo)
1. `/health/ready` saudável quando o banco está na head real (head
   resolvida no teste pela mesma função, sem string hardcoded também
   no teste).
2. `/health/ready` não-saudável (503) quando o banco está uma revisão
   atrás da head — via `run_alembic("0025_god_system_query",
   "downgrade")`, teste nomeado `migration_round_trip` para os hooks
   de guarda do `conftest.py` restaurarem o estado depois.
3. **Regressão do bug original**: o teste cria um arquivo de migration
   real e temporário (`zzzz_health_regr_tmp`, revisão exclusivamente
   de teste, encadeada depois da head real) — confirma que
   `resolve_alembic_head()` já reporta a nova revisão só de o arquivo
   existir em disco (sem nada aplicado ainda), confirma que
   `/health/ready` fica 503 enquanto o banco não alcança essa nova
   head, aplica via `alembic upgrade head` (nenhuma mudança em
   `health.py`) e confirma que `/health/ready` volta a 200 — prova que
   a classe de bug do lote anterior não pode mais acontecer sem
   alteração de código. `finally` desfaz a migration temporária e
   restaura a head real, tanto no banco quanto em disco.

Achado durante a escrita do teste 3: `alembic_version.version_num` é
`varchar(32)`; a primeira revisão de teste escolhida
(`zzzz_test_temp_health_regression_only`, 38 caracteres) estourou a
coluna com `StringDataRightTruncationError` — não é um bug do código
de produção, é uma restrição real do schema que o teste precisa
respeitar. Corrigido encurtando para `zzzz_health_regr_tmp` (21
caracteres).

`python -m ruff check app/api/health.py tests/test_health.py`: **All
checks passed!** `python -m pytest tests/test_health.py -v`: **4
passed** contra `postgres-test` (porta 5433, ~31s) e **4 passed**
contra o `postgres` real (porta 5432, banco `the_creation_os_test`,
~93s — diferença consistente com o custo de fsync já medido no lote de
lentidão da suíte).

### Docker real
`docker compose build api` (imagem reconstruída para incluir o novo
`health.py`) seguido de `docker compose up -d`.

**Segundo bug real, encontrado só na verificação em container** (o
teste unitário e o `import` local não pegam isso, porque ambos rodam
com cwd = `backend/`, um checkout de código-fonte de verdade):
`_BACKEND_ROOT = Path(__file__).resolve().parents[2]` presumia que
`health.py` estaria sempre a exatos dois níveis abaixo da raiz do
backend (`app/api/health.py` → `app` → backend). Isso só é verdade
rodando a partir do checkout local; dentro do container, o `Dockerfile`
instala o pacote via `pip install` a partir de wheels (`COPY --from=builder
/wheels`), então `app/api/health.py` acaba fisicamente em
`/usr/local/lib/python3.12/site-packages/app/api/health.py` — dois
níveis acima disso é `site-packages`, não `/app` (o `WORKDIR` real,
onde `COPY alembic.ini ./` e `COPY alembic ./alembic` de fato colocam
os arquivos). Resultado: `resolve_alembic_head()` procurava
`alembic.ini` dentro de `site-packages`, não encontrava, e
`/health/ready` caía no branch de exceção (503 "could not resolve the
expected Alembic migration head") — confirmado rodando
`docker compose exec api python -c "..."` diretamente e inspecionando
`_BACKEND_ROOT`/`_ALEMBIC_INI`/`_ALEMBIC_SCRIPT_LOCATION` dentro do
próprio container.

Corrigido trocando a resolução baseada em `__file__` por resolução
baseada no diretório de trabalho do processo (`Path.cwd()`) — a mesma
convenção que o próprio `CMD` do container já usa com sucesso
(`python -m alembic upgrade head`, executado com cwd `/app`, onde
`alembic.ini` de fato está) e que os testes/scripts locais também já
seguem (cwd `backend/` por convenção estabelecida no `TESTING.md`).
Reconstruído (`docker compose build api`, segunda vez) e reimplantado.

`docker compose ps`: **6/6 serviços saudáveis**. `curl
http://localhost:8000/api/v1/health/ready`: **`HTTP 200`,
`{"status":"ready"}`** — confirmado contra o stack real rodando, não
só no teste unitário.

### Arquivos alterados
- `backend/app/api/health.py` — `EXPECTED_ALEMBIC_REVISION` removida;
  `resolve_alembic_head()` adicionada.
- `backend/tests/test_health.py` — novo, 4 testes.
- `README.md`, `backend/README.md` — menções de `0024_creator_singleton`
  como head fixa substituídas por texto que descreve a resolução
  dinâmica (fecha a pendência cosmética apontada no lote anterior).

### Achado real fora do escopo deste lote — NÃO corrigido aqui
Ao rodar a suíte completa contra `postgres-test` (`python -m pytest
tests -q`, fora do escopo original mas parte da validação de rotina),
2 testes pré-existentes falharam — sem relação com `health.py` (não
tocado por este lote; `git diff --stat` confirma que só
`app/api/health.py` foi alterado, `test_auth.py` e
`test_migration_0023_seed_idempotency.py` continuam exatamente como
estavam antes deste lote):

- `tests/test_migration_0023_seed_idempotency.py::test_0023_pure_round_trip_from_intermediate_revision_succeeds`
  — linha 57 compara `version_num` contra a string hardcoded
  `"0025_god_system_query"`; ficou desatualizada quando a migration
  0026 foi adicionada (mesma doença deste lote inteiro, mas em código
  de teste). Fix seria trivial (comparar contra a head real resolvida
  dinamicamente, com a própria `resolve_alembic_head()` deste lote).
- `tests/test_auth.py::test_0024_migration_round_trip_singleton_constraint`
  — mais estrutural: o teste assume que `run_alembic("0024_creator_singleton",
  "upgrade")` parte de uma revisão abaixo de 0024, o que era verdade
  quando 0024 ainda era a head (na época em que o teste foi escrito).
  Hoje o hook de guarda do `conftest.py` já restaura o banco para a
  head real (0026) antes do teste rodar, e `alembic upgrade
  <revisão-anterior-à-atual>` é no-op (não retrocede) — o teste
  precisaria de um downgrade explícito antes do upgrade-alvo para
  continuar válido. Não é um problema de ordenação de testes (o mesmo
  lote de fragilidade de ordenação já investigado não cobre este
  caso); é uma suposição que apodreceu conforme a chain de migrations
  cresceu.

Ambos pré-existentes na árvore de trabalho atual (introduzidos, a
julgar pelo conteúdo, nos lotes `SYSTEM_QUERY` e/ou `pgvector`, quando
a migration 0025/0026 foi criada sem atualizar essas duas asserções).
Fora do escopo declarado deste lote (`app/api/health.py`); reportado
para decisão do Criador sobre um lote de correção dedicado.

Também ainda pendente: `docs/RELEASE_CHECKLIST.md` (linhas 111, 124) e
`docs/PROMPT_FINALIZACAO_RC1.md` (linha 152) continuam com checklist
operacional referenciando `0024_creator_singleton` como a head
esperada — mesma classe de menção cosmética do README, mas em docs de
runbook/checklist fora do escopo deste lote (que tratou especificamente
os dois `README.md`). `docs/AUDIT_v0.5.md` e `backend/MIGRATIONS.md`
NÃO precisam de ajuste — são registro histórico/changelog por
migration, não afirmação de estado atual.

## Lote: Corrigir revisão stale em test_migration_0023_seed_idempotency.py e test_auth.py (2026-08-01)

Fecha os dois achados fora de escopo do lote anterior. Mesma doença —
strings de revisão Alembic hardcoded apodrecendo conforme a chain
cresce — mas as duas causas exatas eram diferentes uma da outra, e
nenhuma das duas era o que o nome do teste sugeria à primeira vista.

### Utilitário compartilhado, sem duplicação
`resolve_alembic_head()` (a resolução dinâmica criada no lote anterior
em `app/api/health.py`) foi extraída para `backend/app/db/alembic_utils.py`,
comportamento idêntico (mesmo `Path.cwd()`-based `Config` +
`ScriptDirectory`, mesmo motivo documentado no docstring). `health.py`
agora só faz `from app.db.alembic_utils import resolve_alembic_head` —
sem lógica duplicada. Como é um `from ... import`, o nome continua
acessível como `app.api.health.resolve_alembic_head` (confirmado:
`from app.api.health import resolve_alembic_head as a; from
app.db.alembic_utils import resolve_alembic_head as b; assert a is b`),
então `tests/test_health.py` não precisou de nenhuma mudança.

### Causa exata #1 — `test_migration_0023_seed_idempotency.py::test_0023_pure_round_trip_from_intermediate_revision_succeeds`
Simples: linha 57 comparava `version_num` contra a string hardcoded
`"0025_god_system_query"`. O teste faz `run_alembic("0022_pgvector_extension",
"downgrade")` seguido de `run_alembic("head", "upgrade")` — chega
corretamente na head real (`0026_conscious_memory_vector` hoje), mas a
asserção comparava contra um valor congelado no momento em que o teste
foi escrito (antes da migration 0026 existir). Não é bug de ordenação;
é bug de esquecimento — ninguém atualizou essa string quando 0026 foi
adicionada. Corrigido comparando contra `resolve_alembic_head()`
(import de `app.db.alembic_utils`) em vez da string.

### Causa exata #2 — `test_auth.py::test_0024_migration_round_trip_singleton_constraint`
Mais sutil, não é comparação de string nenhuma — o teste nunca compara
contra "head". A causa real: o teste presumia implicitamente que a
posição do banco *antes* dele rodar seria sempre "em algum ponto ≤
0024" — presunção que era automaticamente verdadeira quando 0024 ERA a
head (o guard hook de `conftest.py`, `pytest_runtest_teardown`, restaura
para head depois de todo teste `migration_round_trip`; e o fixture de
sessão `_migrate_test_database_to_head` faz o mesmo no início da
sessão — então, na época, "início do teste" e "0024" coincidiam por
definição). O primeiro passo do teste era `run_alembic("0024_creator_singleton",
"upgrade")`, um comando que só MOVE PARA FRENTE — nunca para trás.
Quando 0025 e 0026 foram adicionadas, a head real passou a ser
`0026_conscious_memory_vector`, os mesmos guard hooks agora restauram
para 0026 (não mais para 0024) antes deste teste rodar, e "upgrade
para 0024" a partir de uma posição já à frente de 0024 vira no-op —
o banco fica parado em 0026, e a asserção `== "0024_creator_singleton"`
falha sempre, incondicionalmente, independente de ordem de execução
(confirmado: roda sozinho, isolado, falha do mesmo jeito — não é uma
interação com outro teste).

**Não é fragilidade de ordenação no sentido do lote anterior** (aquele
lote tratava de dados residuais de OUTROS testes contaminando um
round-trip; aqui não há contaminação nenhuma, é uma suposição sobre
POSIÇÃO NA CHAIN que ficou implícita e não foi revalidada). Também não
é candidata a virar uma propriedade genérica "downgrade de N para N-1
e upgrade de volta" parametrizada — o teste existe especificamente para
verificar o comportamento de upgrade/downgrade de UMA migration
determinada (0024, a que adiciona `uq_creator_singleton` e
`ck_creator_singleton_true`), então referenciar as revisões `0023` e
`0024` por nome é apropriado e permanece estável para sempre (a aresta
0023→0024 no grafo de migrations é imutável, migrations não são
reescritas). O que faltava era só um passo explícito de downgrade
abaixo de 0024 ANTES do upgrade-alvo, em vez de presumir que o banco já
começaria lá. Corrigido invertendo a ordem das duas metades do teste:
primeiro `run_alembic("0023_universe_agent_seed", "downgrade")` e
confirma ausência das constraints, depois `run_alembic("0024_creator_singleton",
"upgrade")` e confirma presença — autocontido, correto não importa
onde a head real esteja hoje ou no futuro. O `run_alembic(0024, "upgrade")`
redundante que existia só para "restaurar o estado" no final foi
removido — o teste já termina em 0024, e por ter `migration_round_trip`
no nome, o próprio guard hook do `conftest.py` restaura para head no
teardown de qualquer forma.

### Testes reais
`ruff check`: **All checks passed!** (`app/api/health.py`,
`app/db/alembic_utils.py`, `tests/test_migration_0023_seed_idempotency.py`,
`tests/test_auth.py`, `tests/test_health.py`).

Cada teste corrigido, isolado, **5x seguidas contra `postgres-test`**:
`test_0024_migration_round_trip_singleton_constraint` — 5/5 exit 0.
`test_0023_pure_round_trip_from_intermediate_revision_succeeds` — 5/5
exit 0.

Os três arquivos relacionados (`test_auth.py`, `test_migration_0023_seed_idempotency.py`,
`test_health.py`, 9 testes ao todo) rodados **3x com `pytest-randomly`
ativo** (ordem aleatória real, sem `-p no:randomly` — seeds diferentes
a cada rodada): **9/9 passed** nas três rodadas, confirmando que a
correção não depende de ordem específica.

### Arquivos alterados
- `backend/app/db/alembic_utils.py` — novo; `resolve_alembic_head()`
  movida para cá.
- `backend/app/api/health.py` — passa a importar de `app.db.alembic_utils`
  em vez de definir a função localmente.
- `backend/tests/test_migration_0023_seed_idempotency.py` — asserção
  de head hardcoded trocada por `resolve_alembic_head()`.
- `backend/tests/test_auth.py` — `test_0024_migration_round_trip_singleton_constraint`
  reestruturado: downgrade explícito antes do upgrade-alvo.

### Pendências reais
- `docs/RELEASE_CHECKLIST.md` (linhas 111, 124) e
  `docs/PROMPT_FINALIZACAO_RC1.md` (linha 152) continuam mencionando
  `0024_creator_singleton` como head fixa — confirmado que seguem
  documentadas como pendência desde o lote anterior; permanecem fora de
  escopo aqui.

## Lote: P4/P5 — Concorrência real de worker (lease reclaim e retry/backoff) (2026-08-02)

Objetivo: testar reclaim de lease e retry/backoff com **dois processos
reais** de `python -m app.worker`, não em processo único. A auditoria
anterior já tinha provado a lógica correta em processo único
(`test_dispatch_error_paths_expiration_acknowledge_and_release`,
`DispatchService.fail()`); este lote existia especificamente para
fechar o gap "nunca testado com dois processos reais". Fechou — e, ao
fechar, encontrou **três bugs reais de produção** que nenhum teste em
processo único jamais teria pego, porque cada um só se manifesta sob
uma condição que só existe com um processo REAL, de verdade, rodando
sozinho por conta própria.

### Achado arquitetural prévio: SYSTEM_WORKER_UUID é um singleton por design
`app/admin/worker.py` e `docker-compose.yml` (serviço `worker`, sem
`replicas`) confirmam: a arquitetura assume UM único processo worker,
autenticado sempre como a mesma identidade fixa
`SYSTEM_WORKER_UUID`. Rodar dois processos reais `python -m app.worker`
simultâneos com essa identidade compartilhada faria os dois brigarem
pelo mesmo campo `Worker.status`, produzindo resultado indefinido —
não testaria reclaim de verdade, testaria uma corrida espúria.
Resolvido tornando a identidade do worker configurável via variável de
ambiente (`WORKER_UUID`, `WORKER_CREDENTIAL_OVERRIDE` em
`app/worker.py`), com fallback exato para o comportamento de hoje
(`SYSTEM_WORKER_UUID` + `settings.worker_credential`) quando nenhuma
das duas está definida — zero mudança de comportamento em produção. O
teste registra duas identidades novas via `WorkerService.register()`
para cada cenário.

### Timings configuráveis, sem mudar o padrão de produção
`WORKER_LEASE_SECONDS`, `DISPATCH_RETRY_BASE_SECONDS`,
`DISPATCH_RETRY_MAXIMUM_SECONDS` — três novas variáveis de ambiente
lidas em `app/worker.py`, todas com default idêntico ao valor hoje
hardcoded (60s / 30s / 3600s). `AgentExecutionService` ganhou
`retry_base_seconds`/`retry_maximum_seconds` (mesmos defaults) para que
`_finish_failure()` também respeite a configuração — antes só o
`DispatchService.fail()` tinha esses parâmetros, mas nenhum chamador
real os passava. Sem essa mudança, um teste de backoff real precisaria
esperar minutos reais por retry; com ela, o teste usa segundos reais
configurados explicitamente, documentados como tal — não um valor
mágico hardcoded divergindo do padrão de produção sem ninguém
perceber.

### Bug real #1 — DispatchService.lease() nunca commitava a varredura de leases expirados
**O mais grave dos três.** `lease()` varre `expired_leases()` e muda o
`state`/limpa os campos de lease em memória (via ORM), depois tenta
`acquire()`. Com `autoflush=True` (o default do SQLAlchemy — e o que
TODO fixture de teste existente usa, inclusive
`test_dispatch_error_paths_expiration_acknowledge_and_release`),
`acquire()` automaticamente enxerga a mudança da varredura antes de
rodar. Mas `app/db/session.py` — o `AsyncSessionLocal` que o worker
REAL usa em produção — define `autoflush=False` explicitamente. Sob
`autoflush=False`, a varredura fica só em memória, `acquire()` roda
contra os dados ainda não sincronizados, não encontra nada, `lease()`
retorna `(None, None)` sem nunca chamar `commit()` — e a varredura
inteira é descartada (rollback implícito ao fechar a sessão). Repita
para sempre: **um lease expirado nunca seria reclamado por nenhum
worker real em produção**, silenciosamente, porque o teste de
processo único mascarava exatamente essa diferença de configuração de
sessão. Confirmado por reprodução direta e isolada (fora do worker.py,
fora de subprocess) antes de corrigir — ver histórico desta sessão.
Corrigido: `await self.repository.commit()` logo após a varredura, em
`DispatchService.lease()` (`app/services/dispatch.py`).

### Bug real #2 — reclaim colide com execução órfã do worker morto
Com o bug #1 corrigido, o segundo worker real de fato reclama o lease
— mas `AgentExecutionService.create()` falha com "Execution already
exists for this dispatch attempt". Causa: `(dispatch_item_id,
attempt_number)` é UNIQUE (`uq_execution_dispatch_attempt`); reclaim
por expiração de lease NÃO incrementa `attempt_count` (só `fail()`
incrementa — expiração não é uma "falha" no sentido usado ali). Um
worker morto entre `create()` (que já inseriu a linha) e
`acknowledge()`/`fail()` deixa uma linha `agent_executions` órfã
exatamente no `attempt_number` que o PRÓXIMO worker vai tentar usar.
Corrigido em `AgentExecutionService.create()`: antes de inserir,
verifica se já existe uma linha para essa chave; se existir E pertencer
a um `worker_id` diferente do worker atual (que só chega até aqui
porque `_chain()`/`_leased()` já provou que ele segura o lease
*atual* do item — logo a linha antiga é comprovadamente órfã), reusa a
linha (atualiza `worker_id`, reseta `state`, payload, deadline,
preserva `id`/`created_at`/eventos anteriores para auditoria) em vez
de inserir uma segunda. Não usei um novo `event_type`
("execution_resumed"): `ck_execution_event_type`
(migration 0008) é uma CHECK constraint real e fixa — estendê-la é uma
migration, uma decisão maior e separada desta correção; reusei
`"execution_created"`, que já descreve corretamente o que aconteceu do
ponto de vista do novo worker.

### Bug real #3 — worker.py deixava o próprio status preso em "busy" após falha de "sem handler"
Achado testando P5: depois da primeira falha (capacidade sem handler
registrado), o worker nunca mais conseguia reivindicar nada —
`WorkerProtocolError("Worker is not available")` em toda tentativa
seguinte, inclusive o próprio retry do mesmo item. Causa:
`_execute()`'s branch de "sem handler" chamava `dispatch.fail(...)`
diretamente (o `DispatchService`), não `workers.fail(...)` (o
`WorkerService`) — só o segundo reseta `worker.status = "available"`
depois de uma falha; `DispatchService.fail()` sozinho não mexe em
`Worker` nenhum. Corrigido trocando a chamada para `workers.fail(...)`
em `app/worker.py`; `WorkerService.fail()` ganhou `base`/`maximum`
opcionais (mesmos defaults 30/3600, comportamento inalterado para
`app/api/workers.py`'s rota `/fail`) para que o backoff configurável
também se aplique aqui.

### Achado de ambiente (não é bug de produção): stall aparente do asyncio ProactorEventLoop no Windows
Durante a investigação, o loop real do worker (`WorkerProcess.run()`)
parava de progredir silenciosamente após o primeiro ciclo, SEM
crashar, SEM lançar exceção — só em execução real como processo
Windows standalone (reproduzido via `subprocess.Popen`, via
backgrounding do bash, e via `python -m app.worker` direto no
terminal; NUNCA reproduzido chamando a mesma lógica de serviço
diretamente, sem o loop de longa duração). Isolado por bissecção:
adicionar QUALQUER I/O real por ciclo (um `print()`, um
`logger.debug()` de fato emitido) faz o problema desaparecer de forma
confiável; trocar para `WindowsSelectorEventLoopPolicy` não resolveu
sozinho. Não investiguei mais fundo que isso (não é o escopo deste
lote, e o deploy real roda em Linux/Docker via `epoll`, não Proactor —
plausivelmente este stall específico do IOCP simplesmente não existe
lá). Mitigado com um `logger.debug("no claimable dispatch item,
sleeping %ss", ...)` real, sempre emitido, adicionado ao loop
(`app/worker.py`) — barato, operacionalmente útil por si só
(visibilidade de que o worker está vivo e ocioso quando alguém liga
`LOG_LEVEL=DEBUG`), e resolve o stall de fato neste ambiente. Os testes
definem `LOG_LEVEL=DEBUG` nos processos worker que sobem. Registrado
aqui como pendência de investigação, não como bug corrigido — a causa
raiz exata (por que Windows/IOCP especificamente) não foi determinada.

### Decisões de design do teste (`backend/tests/test_worker_concurrency.py`)
- **A e B não sobem simultaneamente no P4.** Subir os dois ao mesmo
  tempo cria uma corrida por "quem reivindica primeiro" — não é o que
  P4 pede ("worker A reivindica, morre, worker B reclama"). B só é
  criado depois que o teste confirma que A segurou o lease e mata A —
  assim, qualquer claim de B só pode ser um reclaim genuíno.
- **Capacidade dedicada `concurrency_test` + handler
  `concurrency_test_echo`** (novo, em `app/agents/handlers.py`), em vez
  de `"planning"`/`structured_echo`: o handler real completa um ciclo
  claim→acknowledge em menos de 150ms localmente — mais rápido que
  qualquer intervalo de poll prático consegue observar de forma
  confiável o item em estado `"leased"` antes de já ter terminado. O
  handler de teste aceita um atraso configurável via
  `CONCURRENCY_TEST_HANDLER_DELAY_SECONDS` (default 0 — zero efeito em
  qualquer deploy real); o teste usa 3s, dando margem confortável para
  observar e matar o worker A antes que ele termine sozinho.
- **P5 usa uma capacidade só com nome, sem handler registrado**
  (`f"flaky_test_{uuid4().hex[:8]}"`) — a via mais simples e reversível
  para "falha determinística até `max_attempts`", per seção 6 do
  prompt: zero código de produção novo, aproveita o caminho já
  existente de `_execute()` para capability sem handler.
- **`_reset_dispatch_queue()`**: os dois testes rodam contra um banco
  persistente compartilhado (não fazem `TRUNCATE` de `creator` — que
  tem singleton real — nem de outras tabelas usadas por outros
  testes), então um item deixado na fila por uma execução anterior
  deste MESMO arquivo é um alvo de corrida real para os workers recém
  criados de uma execução seguinte. `TRUNCATE dispatch_items,
  dispatch_attempts ... CASCADE` no início de cada teste (cascata
  automática do Postgres cobre `agent_executions`/
  `agent_execution_events` também).
- **Marker `concurrency`** registrado em `pyproject.toml` (além de
  `integration`) — não adicionado a nenhum `addopts` (o padrão deste
  projeto já é rodar a suíte inteira, incluindo testes reais de
  Postgres, sem exclusão por default). Operador pode excluir
  especificamente estes dois com `-m "not concurrency"` quando quiser
  uma iteração mais rápida.

### Resultados reais
`ruff check` (todos os arquivos tocados): **All checks passed!**

Regressão (nenhuma quebra pelas correções em `dispatch.py`/
`execution.py`/`workers.py`/`worker.py`/`handlers.py`):
`test_dispatch_integration.py`, `test_dispatch_service.py`,
`test_execution_integration.py`, `test_handler_registry.py`,
`test_knowledge_memory_integration.py`, `test_tree_core_postgres.py`,
`test_worker_orchestration.py`, `test_worker_protocol.py` — **34/34
passed**.

P4 isolado, `postgres-test`: **5/5 execuções, todas passed** (~18s
cada). P5 isolado, `postgres-test`: **5/5 execuções, todas passed**
(~14s cada). Os dois juntos, `postgres-test`, **com pytest-randomly
ativo (ordem aleatória real, seeds diferentes)**: **3/3 execuções,
2/2 passed cada** (~24s cada). Os dois juntos contra `postgres` real
(porta 5432, não `postgres-test`): **2/2 passed em 38s**.

**Zero processo órfão**: `Get-Process python` (PowerShell) depois de
cada rodada de validação — nenhum processo Python remanescente em
nenhuma das checagens.

### Tempo real adicionado à suíte
P4+P5 juntos: **~24s em `postgres-test`, ~38s em `postgres` real** —
dominado por esperas reais de wall-clock (expiração de lease, delay do
handler de teste, backoff), não por overhead de fsync/commit (por isso
a diferença `postgres-test` vs `postgres` real é bem menor aqui do que
no resto da suíte — a maior parte do tempo é `asyncio.sleep`, não
I/O). Marcado como `concurrency` (ver acima) para quem quiser excluir
deliberadamente; não excluído do `addopts` padrão.

### Arquivos alterados/criados
- `backend/app/worker.py` — `WORKER_UUID`/`WORKER_CREDENTIAL_OVERRIDE`/
  `WORKER_LEASE_SECONDS`/`DISPATCH_RETRY_BASE_SECONDS`/
  `DISPATCH_RETRY_MAXIMUM_SECONDS` configuráveis; branch de "sem
  handler" agora usa `workers.fail()`; log de debug por ciclo.
- `backend/app/services/dispatch.py` — commit após a varredura de
  leases expirados em `lease()` (bug #1).
- `backend/app/services/execution.py` — `retry_base_seconds`/
  `retry_maximum_seconds` configuráveis; `create()` reusa execução
  órfã em vez de colidir (bug #2).
- `backend/app/services/workers.py` — `fail()` aceita `base`/`maximum`
  opcionais (bug #3).
- `backend/app/repositories/execution.py` — novo método
  `for_attempt()`.
- `backend/app/agents/handlers.py` — novo handler/capacidade só de
  teste `concurrency_test_echo`/`"concurrency_test"`.
- `backend/pyproject.toml` — marker `concurrency` registrado.
- `backend/tests/test_worker_concurrency.py` — novo, P4 + P5.

### Pendências reais
- Causa raiz exata do stall do asyncio/ProactorEventLoop no Windows
  não determinada (só mitigada). Não deve afetar produção
  (Linux/Docker), mas vale investigar mais a fundo se voltar a
  aparecer em CI Windows, se existir algum dia.
- A extensão de `ck_execution_event_type` para incluir um `event_type`
  dedicado ("execution_resumed" ou similar) para o caminho de reclaim
  de execução órfã (bug #2) ficou de fora — reusei `"execution_created"`
  deliberadamente para não decidir unilateralmente uma mudança de
  schema; um lote futuro pode avaliar se vale a pena distinguir os dois
  casos na auditoria de eventos.
- `docs/RELEASE_CHECKLIST.md` e `docs/PROMPT_FINALIZACAO_RC1.md`
  seguem com a menção cosmética a `0024_creator_singleton` — mesma
  pendência de lotes anteriores, ainda fora de escopo aqui.

## Lote: event_type dedicado para reclaim de lease (2026-08-02)

Fecha a pendência do lote P4/P5 anterior: um `event_type` específico
para quando `AgentExecutionService.create()` reaproveita (em vez de
recriar) uma execução órfã deixada por um worker morto — antes disso
reusava `"execution_created"`, indistinguível da criação normal.

### Discrepância real encontrada antes de implementar
O prompt deste lote presumia que a tabela relevante ("Chronicles")
armazena `event_type` como string livre, sem necessidade de migration.
Verificado: a tabela `chronicles` de fato (`app/models/entities.py`,
migration `0001_initial`) realmente não tem CHECK constraint — mas o
evento em questão não vive lá. Ele vive em `agent_execution_events`
(`app/models/execution.py`), que **tem** uma CHECK constraint real e
fixa (`ck_execution_event_type`, migration `0008_agent_execution`)
enumerando literalmente os valores aceitos. Um `event_type` novo ali
exige migration — contrariando a instrução explícita da seção 4 do
prompt. Também não foi possível localizar "prompt original v0.3 seção
12" no repositório: é um artefato externo, não versionado (mesma
categoria já registrada em ARCHITECTURE.md, nota sobre
`docs/PROMPT_INCREMENTO_COMPLETO.md`). Reportado ao Criador antes de
prosseguir; decisão: fazer a migration pequena.

### Nome escolhido: `execution_reclaimed`
Segue a convenção já usada por todo o resto do enum
(`execution_created`, `execution_accepted`, `execution_started`,
`execution_succeeded`, `execution_failed`, `execution_cancelled`,
`execution_timed_out`) — todos no padrão `execution_<particípio>`,
exceto o único outlier pré-existente `result_returned`. `reclaimed`
descreve exatamente o que aconteceu do ponto de vista do novo worker:
ele reclamou (reclaim) uma execução abandonada, não criou uma nova.

### Migration `0027_execution_reclaimed_event`
Segue o precedente exato de `0025_god_system_query` (mesmo padrão:
`drop_constraint` + `create_check_constraint` com a lista estendida).
`upgrade()`: adiciona `'execution_reclaimed'` à lista.
`downgrade()`: remove, restaurando a lista original de `0008`.

### Antes/depois (`app/services/execution.py`, branch de resume em `create()`)
Antes:
```python
# Not a new "execution_resumed" event type: ck_execution_event_type
# ... extending it is a schema migration, a bigger and separate
# decision than this fix. "execution_created" already accurately
# describes what just happened ... so it's reused here.
await self._event(existing, "execution_created", worker)
await self.repository.commit()
```
Depois:
```python
# Dedicated event_type — distinct from "execution_created" (the
# normal, first-attempt path below) — so consumers can tell a
# resumed/reclaimed attempt apart from a fresh one.
# ck_execution_event_type (migration 0027_execution_reclaimed_event)
# was extended specifically for this.
await self._event(existing, "execution_reclaimed", worker)
await self.repository.commit()
```

### Consumidores verificados
Busca exaustiva por `"execution_created"`, `AgentExecutionEvent`, e
`agent_execution_events` em `app/` inteiro: só existem em
`app/services/execution.py` (onde o evento é emitido) e
`app/repositories/execution.py` (a query genérica `events()`, que
retorna a lista crua sem filtrar por tipo — não precisa mudar).
Nenhuma referência em `app/services/pulse.py`, `app/core/god.py`
(SYSTEM_QUERY), nem em nenhuma outra rota/serviço. **Nenhum
consumidor real precisou ser atualizado** — o único lugar que já
fazia asserção sobre a sequência exata de eventos
(`tests/test_execution_integration.py`, o caminho normal, sem
reclaim) continua correto sem alteração, porque não emite
`execution_reclaimed`.

### Achado real durante a escrita do teste — bug de timing no próprio teste (não em produção)
O teste de P4 matava o worker A assim que o `DispatchItem` chegava a
`state=="leased"` — mas esse estado é setado por `workers.claim()`
*antes* de `execution_service.create()` sequer rodar. Isso tornava
não-determinístico se A conseguia ou não commitar sua própria linha
de execução antes de ser morto: quando não conseguia, não havia nada
órfão para B reclamar (o `create()` de B simplesmente inseria uma
linha nova, sem `execution_reclaimed`) — falha intermitente real
observada (~1 em 3–4 execuções) só na asserção nova, não na lógica de
produção. Confirmado via inspeção direta do banco (uma única linha
`agent_executions`, criada pelo worker B, sem nenhuma órfã de A) e dos
logs de ambos os processos lado a lado. Corrigido fazendo o teste
esperar a linha `agent_executions` realmente existir (não só o
`DispatchItem` estar `"leased"`) antes de matar A — garante
deterministicamente que o cenário de execução órfã sempre acontece.
Aumentei também a margem do handler de teste
(`CONCURRENCY_TEST_HANDLER_DELAY_SECONDS`, 3s → 6s) e do
`lease_seconds` (6s → 10s) por segurança adicional contra variação de
agendamento do SO.

### Testes reais
`ruff check` (todos os arquivos tocados): **All checks passed!**

Novo: `tests/test_worker_concurrency.py::test_p4_lease_reclaim_two_real_worker_processes`
agora também confirma `execution_reclaimed` — exatamente uma vez,
depois de exatamente um `execution_created`, terminando em
`execution_succeeded`/`result_returned`. **10/10 execuções passed**
(após a correção do timing do teste).

Regressão completa (P4+P5+execution+dispatch+handler_registry+worker_orchestration+worker_protocol),
`postgres-test`: **29/29 passed**. Validação adicional contra
`postgres` real (porta 5432): **2/2 passed** (P4+P5).

`test_execution_integration.py` (caminho normal, sem reclaim) — **sem
regressão**: sequência continua `execution_created, execution_accepted,
execution_started, execution_succeeded, result_returned`, sem
`execution_reclaimed`.

**Zero processo órfão**: `Get-Process python` (PowerShell) depois de
cada validação.

### Arquivos alterados/criados
- `backend/alembic/versions/0027_execution_reclaimed_event.py` — novo,
  estende `ck_execution_event_type`.
- `backend/app/services/execution.py` — `create()`'s branch de resume
  emite `"execution_reclaimed"` em vez de `"execution_created"`.
- `backend/tests/test_worker_concurrency.py` — novas asserções sobre
  `AgentExecutionEvent`; correção do timing do kill de A (aguarda a
  linha de execução existir, não só o lease); margens de tempo
  ajustadas.

### Pendências reais
- Nenhuma pendência nova de schema/consumidor identificada.
- Rebuild/redeploy do `docker compose` (api + worker) com a migration
  e as mudanças de código — ver confirmação abaixo desta seção.

## Processo: hábito de revisão periódica de documentação (2026-08-02)

### Revisão periódica de documentação

Motivo: divergências entre documentação e implementação real
apareceram repetidamente nesta sequência de lotes, sempre descobertas
incidentalmente, nunca por checagem dedicada.

Regra: a cada 5 lotes de implementação concluídos (não documentais),
ou antes de qualquer marco de release (RC1, RC2, etc.), rodar uma
checagem rápida e explícita:
1. Grep por nomes de evento, nomes de tabela, e identificadores centrais
   citados em docs/*.md e ARCHITECTURE.md contra o código-fonte real,
   confirmando que ainda existem com esse nome exato.
2. Releitura das seções "Decisões congeladas" e "Arquitetura" de
   ARCHITECTURE.md contra o estado atual do código, marcando qualquer
   item que precise de atualização.
3. Reportar divergências encontradas, mesmo que pequenas, em vez de
   corrigir silenciosamente — cada uma deve ter sua própria linha de
   decisão (corrigir agora vs. registrar como pendência).

Esta checagem não substitui a auditoria completa de um lote específico
— é uma rede de segurança mais barata e frequente entre auditorias
maiores.

## Lote: Calibração de parâmetros HNSW para volume de produção real (2026-08-02)

Investiga se os parâmetros default do índice HNSW em
`conscious_memory.embedding` (`m=16, ef_construction=64`, migration
`0026_conscious_memory_vector`) seguram em volume bem acima dos 2000
registros sintéticos medidos no lote original (`test_conscious_memory_ann_performance.py`).
Não presumiu que precisaria mudar algo — mediu primeiro.

### Estimativa de volume de produção — não havia nenhuma documentada
Busca em `ARCHITECTURE.md`/`docs/*.md` não encontrou nenhuma estimativa
real ou projetada de volume de `conscious_memory` em produção — só a
linguagem vaga já registrada na entrega do índice HNSW ("escala de
milhares de linhas esperada"). Proposta de faixa razoável, baseada no
código real: `ConsciousMemoryService._consolidate()` só é chamado a
partir de `consolidate_from_mission()` (uma Mission alcança
`manifested`) ou `consolidate_explicit()` (decisão explícita do
Creator) — e `creator` é uma tabela singleton real
(`uq_creator_singleton`, migration 0024): este é um sistema de um único
usuário, não multi-tenant. Mesmo um uso diário muito ativo (20-30
missões/decisões por dia, um teto generoso para a capacidade de um
único humano conceber/autorizar/revisar objetivos estratégicos
distintos) daria 7.300-10.950 linhas/ano — os 100.000 testados aqui
representariam algo entre 9-14 anos de uso contínuo nesse ritmo
extremo, ou uma faixa muito mais confortável de tempo num ritmo
realista (poucas missões por dia). **100.000 é um teto de longo prazo
razoável para calibrar contra, não um volume esperado no primeiro
ano.**

### Metodologia
Reaproveitado o gerador determinístico de embeddings
`_embedding()` de `test_conscious_memory_ann_performance.py` (importado
diretamente, não reimplementado) e o padrão de fixture (TRUNCATE + bulk
insert + ANALYZE) do mesmo arquivo. Novo arquivo,
`tests/test_conscious_memory_hnsw_calibration.py`, marcado
`benchmark` (novo marker, registrado em `pyproject.toml` junto de
`concurrency`) — não roda por padrão junto da suíte comum; exclua
explicitamente ou rode a suíte inteira, que já roda tudo por default
neste projeto.

Para cada volume: bulk insert em lotes de 5000 linhas, `DROP INDEX` +
`CREATE INDEX ... WITH (m=.., ef_construction=..)` cronometrado do
zero, `ANALYZE`, então:
- **Latência**: 10 embeddings de consulta distintos × 10 chamadas cada
  (100 chamadas, média), via `ConsciousMemoryRepository.search_by_embedding()`
  real (o mesmo caminho de produção).
- **Recall@10**: 20 embeddings de consulta distintos, comparando o
  top-10 aproximado (HNSW) contra o top-10 EXATO — obtido com
  `SET LOCAL enable_indexscan = off; enable_bitmapscan = off` na mesma
  sessão, forçando Seq Scan (o operador `<=>` de distância de cosseno é
  sempre exato; só quais candidatos o índice examina é aproximado).
  Overlap médio dos IDs, não presumido.

### Resultados reais — parâmetros atuais (m=16, ef_construction=64)

| Volume (linhas) | Build do índice | Latência de busca | Recall@10 |
|---:|---:|---:|---:|
| 5.000 | 3.01s | 3.35ms/chamada | 1.000 |
| 20.000 | 25.52s | 3.48ms/chamada | 1.000 |
| 100.000 | 129.73s | 4.26ms/chamada | 1.000 |

(Tempo de população dos dados sintéticos, não relevante à calibração
em si — custo de setup do benchmark, não da busca: 10.09s / 43.28s /
477.37s respectivamente.)

Comando real: `python -m pytest
"tests/test_conscious_memory_hnsw_calibration.py::test_hnsw_default_params_at_volume[N]"
-q -p no:randomly -s`, contra `postgres-test`.

### Decisão: manter os parâmetros default
Recall permaneceu **perfeito (1.000)** nos três volumes — zero
divergência entre o resultado aproximado do HNSW e a busca exata, em
nenhum dos 60 pares consulta×volume testados (20 consultas × 3
volumes). Latência cresceu de forma sub-linear e continua na casa de
poucos milissegundos mesmo em 100.000 linhas (50x o benchmark anterior)
— nenhuma degradação preocupante em nenhuma das duas métricas de
runtime. Por instrução explícita da seção 4 do lote, nenhuma
configuração alternativa foi testada, porque não havia degradação a
resolver — testar `m`/`ef_construction`/`ef_search` maiores aqui seria
mudança sem motivo medido. `m=16, ef_construction=64` permanecem
inalterados; nenhuma migration nova.

O único número que merece atenção operacional, não de calibração de
qualidade de busca: **build do índice em ~130s a 100k linhas** —
irrelevante para o volume atual (zero linhas em produção), mas relevante
se algum dia for necessário fazer um `REINDEX`/rebuild manual num banco
já grande; não é um problema de query nem de recall, só o custo
one-time de reconstrução.

### Arquivos alterados/criados
- `backend/tests/test_conscious_memory_hnsw_calibration.py` — novo,
  3 casos parametrizados (5k/20k/100k), marcado `integration` +
  `benchmark`.
- `backend/pyproject.toml` — novo marker `benchmark` registrado.

### Pendências reais
- Reavaliar quando o volume real de produção for conhecido de fato —
  os números aqui são calibração preventiva contra volumes projetados,
  não medição contra tráfego real (que hoje é zero linhas).
- Se o volume real algum dia se aproximar de dezenas de milhares de
  linhas, considerar automatizar o `REINDEX`/rebuild como parte de uma
  rotina de manutenção — não implementado aqui por ser expansão de
  escopo explicitamente fora deste lote (seção 4 do prompt).

## Auditoria: Seção 3 — Autenticação, Chronicles/verify, Segurança mínima, Observabilidade (2026-08-02)

Itens do escopo original v0.3 nunca revisitados por uma auditoria
dedicada nesta sequência de lotes — só tocados incidentalmente. Achado
real e significativo: um bug de produção genuíno em `GET
/api/v1/auth/me` (404 para todo chamador válido), encontrado
precisamente porque este lote escreveu o teste que faltava para um
comportamento presumido correto.

### 2a. Chronicles — verificação de cadeia de hashes — SEM GAP
`GET /api/v1/chronicles/verify` existe (`app/api/creator_interface.py`),
protegido por `get_sovereign_creator`. Chama
`DomainRepository.verify_chronicle()` (`app/repositories/domain.py`),
que percorre a cadeia inteira por `position`, confere
`previous_hash` contra o hash do evento anterior, e recomputa
`event_hash()` (SHA-256 do material canônico) comparando contra
`payload_hash` armazenado — detecção real de adulteração, não um
status fixo. `tests/test_postgres_integration.py::test_chronicle_verifier_detects_tampering`
adultera `payload_json` de um evento já persistido diretamente no
banco e confirma que `verify_chronicle()` retorna `valid=False,
reason="invalid event hash"` — não só o caminho feliz;
`test_concurrent_chronicle_appends_are_linear` cobre a cadeia íntegra
sob concorrência real (`asyncio.gather`).

### 2b. Autenticação do Criador — 1 BUG REAL ENCONTRADO E CORRIGIDO, 1 GAP GRANDE
- **Bootstrap**: `AuthService.bootstrap()` (`app/services/auth.py`)
  faz check-then-insert, mas o guard real é `uq_creator_singleton`
  (migration 0024) — uma segunda tentativa concorrente é pega por
  `IntegrityError`, capturada e traduzida para 409 limpo (`raise
  HTTPException(...) from exc`, sem stack trace vazando ao cliente —
  confirmado também pelo handler global de exceções, seção 2c).
  Testado (`test_bootstrap_rejects_second_creator_sequential`,
  `test_bootstrap_rejects_second_creator_concurrent`, ambos já
  existentes).
- **Hash de senha**: `bcrypt.hashpw()`/`bcrypt.checkpw()` com salt
  aleatório por hash (`app/repositories/auth.py`) — algoritmo forte,
  padrão da indústria. Limite de 72 bytes do bcrypt tratado
  explicitamente (rejeita senha longa demais em vez de truncar
  silenciosamente — evita uma pegadinha conhecida do bcrypt).
- **Anti-enumeração no login**: `AuthService.login()` usa um único
  branch (`creator is None or not verify_password(...)`) que sempre
  levanta a MESMA mensagem/status ("Invalid credentials", 401) — não
  revela se o problema foi usuário ou senha. Confirmado por teste novo
  contra o HTTP real (`test_login_rejects_wrong_username_and_wrong_password_identically`).
- **JWT**: `create_token()` (`app/services/auth.py`) inclui `sub`,
  `type`, `exp`, `jti` — expiração real e finita
  (`settings.access_token_expires` = 15min,
  `settings.refresh_token_expires` = 24h via `app/config.py`, não
  infinita por engano). `jose.jwt.decode()` valida `exp`
  automaticamente (biblioteca madura, não código próprio). Verificação
  de tipo de token: `get_current_creator()` exige `type=="access"`,
  `/refresh` exige `type=="refresh"` — um refresh token não funciona
  como access token e vice-versa, confirmado por dois testes novos
  contra o HTTP real.
- **BUG REAL ENCONTRADO E CORRIGIDO — `GET /api/v1/auth/me` sempre
  retornava 404 para todo chamador válido.** `login()`/`refresh()`
  chamam `create_access_token(creator.id)` — `sub` é o **id** do
  Creator, não o username. `me()` (`app/auth/routes.py`) chamava
  `auth_service.repository.get_by_username(token_payload.sub)` —
  procurando um UUID na coluna `username`, que nunca bate. Descoberto
  pelo teste novo escrito para este lote (falhou com 404 em vez de
  200 na primeira execução real); corrigido trocando para
  `get_by_id(token_payload.sub)` (método já existente em
  `CreatorRepository`). Não usado hoje pelo frontend (`grep` em
  `frontend/src` não encontra nenhuma chamada a `/auth/me`) — sem
  impacto de usuário observado até agora, mas era um endpoint
  documentado e completamente quebrado.
- **GAP GRANDE, NÃO IMPLEMENTADO — rate limiting no login não existe.**
  Busca exaustiva (`grep -rn "rate.limit\|RateLimit\|slowapi\|limiter\|throttle"`
  em todo `app/`) não encontra nenhum mecanismo de rate limiting em
  lugar nenhum do backend — a única ocorrência (`app/services/perception.py`)
  é sobre limitar chamadas a APIs externas de percepção, não sobre
  login. `/auth/login` aceita tentativas ilimitadas. Reportado, não
  implementado — decisão real de mecanismo (Redis já disponível vs.
  em memória — em memória não sobrevive a restart nem funciona
  corretamente com múltiplos processos API), de chave (por IP? por
  username? global?) e de resposta (429 com que janela/backoff?) que
  não deve ser presumida.

### 2c. Segurança mínima — 1 GAP GRANDE, 1 GAP PEQUENO CORRIGIDO
- **CORS — GAP GRANDE, NÃO IMPLEMENTADO.** `app/main.py`:
  `CORSMiddleware(allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])`
  — hardcoded, incondicional, sem leitura de `APP_ENV`/variável de
  ambiente nenhuma. `allow_origins=["*"]` combinado com
  `allow_credentials=True` é um anti-padrão conhecido e sinalizado pela
  OWASP (na prática, a maioria dos browsers recusa enviar credenciais
  para uma resposta CORS com origem `*` — mas a política *declarada*
  pelo servidor continua incorreta e não é validada nem restrita por
  ambiente). Reportado, não corrigido: exige saber a origem real do
  frontend em produção (não presumida aqui) e decidir a política exata
  por ambiente — proposta: `cors_allowed_origins` configurável via
  env var, default restritivo fora de `development`.
- **Headers de segurança — GAP PEQUENO, CORRIGIDO.** Busca exaustiva
  (`X-Content-Type-Options`, `X-Frame-Options`,
  `Strict-Transport-Security`, `X-XSS-Protection`,
  `Content-Security-Policy`, `Referrer-Policy`) não encontrava
  nenhuma ocorrência em `app/` antes desta auditoria. Adicionado
  middleware `add_security_headers` (`app/main.py`) com
  `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
  `Referrer-Policy: no-referrer` — mecânico, sem decisão de política
  pendente, sem risco de quebrar nada existente. Deliberadamente FORA:
  `Strict-Transport-Security` (o stack roda em HTTP puro em
  dev/docker-compose hoje; um browser cacheando esse header local
  passaria a forçar HTTPS nesse host, quebrando acesso dev) e
  `Content-Security-Policy` (uma política errada quebra o frontend
  real; exige conhecer exatamente que origens/scripts/estilos ele
  carrega — informação que esta auditoria não tem). Testado
  (`test_security_headers_present_on_every_response`).
- **Sanitização de logs**: `SENSITIVE_KEYS`/`sanitize()`
  (`app/repositories/domain.py`) é aplicado a `Chronicle.payload_json`
  na escrita (`add_event()`). `log_blocked_action`
  (`app/observability/security.py`, único outro ponto usando `loguru`
  no projeto inteiro) só registra campos fixos e nomeados (actor_id,
  action, resource, correlation_id, reason) — nenhum payload livre, sem
  necessidade de sanitização adicional ali. Não existe nenhum "logging
  estruturado geral da aplicação" além desses dois pontos — ver 2d.
- **Tratamento global de exceções — SEM GAP.**
  `@app.exception_handler(Exception)` em `app/main.py` é um catch-all
  genuíno: qualquer exceção não tratada especificamente retorna só
  `{"detail": "Internal server error"}` com 500 — nenhum stack trace,
  nenhum detalhe interno vazado. `DomainError`/`NotFoundError` têm
  handlers dedicados que retornam mensagens curtas e controladas
  (`str(exc)` de exceções com mensagens escritas à mão, não dumps de
  exceção). Bootstrap's `IntegrityError` já confirmado tratado
  graciosamente (2b).

### 2d. Observabilidade granular — GAP GRANDE, NÃO IMPLEMENTADO (mapeamento real)
Pulse (`app/services/pulse.py::build_pulse_snapshot()`) hoje expõe:
status de database/redis, integridade da cadeia Chronicles,
`active_universes`, `active_agents`, `running_missions`,
`pending_inceptions`, `pending_tasks`, `failed_tasks`, `error_count`
(eventos Chronicle com "failed" no `event_type`).

**Falta, confirmado por ausência (não por suposição)**:
- Contagem/taxa de requests HTTP e latência — nenhuma métrica, nenhum
  middleware de timing em `app/main.py` ou em lugar nenhum.
- Inceptions **aprovados** especificamente (Pulse só tem "pending":
  proposed/submitted/pending — não distingue aprovados de propostos).
- Missões **criadas** (total) — Pulse só tem "running" (planned/
  authorized/running), não um total histórico nem breakdown por
  status.
- Tarefas **concluídas** (Pulse tem `pending_tasks`/`failed_tasks`,
  falta `completed_tasks`/succeeded).
- Tamanho real da fila de dispatch (`dispatch_items` em
  queued/retry_scheduled) — diferente de `pending_tasks`, que é
  estado de planejamento (Task), não profundidade da fila de execução
  (DispatchItem).

**Logging JSON estruturado — não existe como prática geral.** `loguru`
é usado em exatamente UM lugar do projeto inteiro
(`app/observability/security.py::log_blocked_action`), e mesmo esse
ponto não tem nenhuma configuração explícita (`logger.add(...,
serialize=True)` ou equivalente) confirmando saída em JSON — o resto
da aplicação usa o logging default do Uvicorn/Starlette (texto plano,
sem os campos exigidos pelo documento original: service, event,
aggregate_type, aggregate_id, etc.). Reportado como gap real e
substancial — implementar um pipeline de logging estruturado
consistente é uma mudança de escopo real, não um "pequeno fix seguro".

**Propagação de correlation_id — SEM GAP na parte auditada.**
Confirmado em 13 arquivos de rota (`app/api/*.py`) que cada um define
sua própria dependency `correlation_id` lendo o header
`X-Correlation-ID` da request quando presente, gerando um novo
`uuid4()` só como fallback — o valor realmente usado no evento
Chronicle é o mesmo que veio da request HTTP, não descartado. Achado
secundário, menor, não corrigido: `add_correlation_id` (middleware em
`app/main.py`) só ecoa de volta o que o cliente enviou (string vazia
se o cliente não mandou nada) — não reflete de volta o UUID
efetivamente gerado internamente quando o cliente não envia um. Não é
falha de segurança, é uma lacuna de observabilidade client-side menor;
corrigi-la exigiria fiar o valor de cada dependency de rota até o
middleware (`request.state`), tocando os 13 arquivos — fora do escopo
de "pequeno fix seguro" desta auditoria.

### Achado incidental — não corrigido
`app/services/auth.py:53`: `datetime.utcnow()` — API depreciada do
Python (`DeprecationWarning` real, visto na saída dos testes). Não é
um problema de segurança nem funcional hoje; comportamento inalterado
até a remoção efetiva em uma versão futura do Python. Reportado como
pendência pequena, não corrigido aqui (fora do escopo direto desta
auditoria de segurança/observabilidade).

### Testes reais
`ruff check` (todos os arquivos tocados): **All checks passed!**

`tests/test_auth.py` (8 testes, 5 novos + 1 corrigido de quebrado para
passando): **8/8 passed**. `tests/test_auth.py` + `tests/test_http_integration.py`
juntos: **13/13 passed**, contra `postgres-test`.

### Arquivos alterados/criados
- `backend/app/auth/routes.py` — corrige `/me` (`get_by_username` →
  `get_by_id`).
- `backend/app/main.py` — middleware `add_security_headers` novo.
- `backend/tests/test_auth.py` — 5 testes novos (login sucesso/anti-
  enumeração, `/me` sucesso+tipo errado, `/refresh` sucesso+tipo
  errado, headers de segurança).

### Pendências reais (gaps grandes, reportados, não implementados)
1. **CORS hardcoded `allow_origins=["*"]` + `allow_credentials=True`**,
   sem variação por ambiente — proposta: `cors_allowed_origins`
   configurável, default restritivo fora de `development`. Precisa da
   origem real do frontend em produção, que não foi presumida aqui.
2. **Rate limiting ausente em `/auth/login`** — precisa de decisão de
   mecanismo (Redis vs. memória), chave (IP/username/global), e
   resposta (429 com que janela).
3. **Logging JSON estruturado não existe como prática geral** — só um
   ponto isolado usa `loguru`, sem confirmação de saída JSON; o resto
   usa o log default do Uvicorn.
4. **Métricas de observabilidade incompletas** — sem requests/latência
   HTTP, sem Inceptions aprovados distintos, sem total de Missões
   criadas, sem tarefas concluídas, sem profundidade real da fila de
   dispatch.
5. **`add_correlation_id` não reflete o UUID gerado internamente**
   quando o cliente não envia um — lacuna menor de observabilidade
   client-side, não de segurança.
6. `datetime.utcnow()` depreciado em `app/services/auth.py` —
   cosmético/futuro, sem urgência.

## Lote: CORS por ambiente + rate limiting no login (2026-08-02)

Fecha duas pendências reportadas na auditoria de segurança anterior.

### Parte A — CORS configurável por ambiente

`app/main.py` tinha `CORSMiddleware(allow_origins=["*"], allow_credentials=True)`
hardcoded e incondicional — anti-padrão sinalizado pela própria OWASP,
sem nenhuma variação por `APP_ENV`.

**Origem real de dev confirmada, não presumida**: `frontend/vite.config.ts`
define `server.port = 5173` explicitamente; `docker-compose.yml` mapeia
o container do frontend (Nginx) para a mesma porta `5173` no host
(`"5173:8080"`). Default de desenvolvimento/teste:
`http://localhost:5173` + `http://127.0.0.1:5173` (as duas formas,
já que browsers tratam `localhost` e `127.0.0.1` como origens
distintas).

**Implementação**:
- `Settings.cors_allowed_origins: str | None` (`app/config.py`) — nova
  variável `CORS_ALLOWED_ORIGINS`, lista separada por vírgula.
- `Settings.cors_allowed_origins_list` (property) — resolve a string
  em lista; se vazia/ausente, cai no default de dev acima.
- `@validator("cors_allowed_origins", always=True)` — levanta
  `ValueError` se `app_env == "production"` e nenhum valor foi
  configurado, seguindo o mesmo padrão já usado por
  `@validator("app_env")` no mesmo arquivo. Sem fallback silencioso
  para permissivo em produção — a aplicação falha ao instanciar
  `Settings()`, antes de qualquer rota existir.
- `resolve_cors_middleware_kwargs(origins: list[str]) -> dict`
  (`app/config.py`) — função pura, isolada especificamente para ser
  testável sem depender do carregamento do FastAPI app inteiro:
  `allow_credentials` é sempre `False` se `"*"` estiver na lista,
  incondicionalmente — mesmo que um operador configure isso
  explicitamente, a combinação perigosa nunca é permitida, com aviso
  via `logger.warning(...)` em vez de falha silenciosa.

**Confirmação real**: `"*"` + `allow_credentials=True` nunca coexistem
— testado diretamente (`test_wildcard_origin_never_coexists_with_allow_credentials`)
chamando `resolve_cors_middleware_kwargs(["*"])` e confirmando
`allow_credentials is False`.

**Pendência real — origem de produção não determinada**: não foi
possível descobrir no repositório o domínio real onde o frontend será
hospedado em produção (nenhuma menção a um domínio de produção real em
`docker-compose.yml`, `.env.example`, ou documentação). `.env.example`
(ambos, raiz e `backend/`) foi atualizado só com o default de
desenvolvimento confirmado (`http://localhost:5173,http://127.0.0.1:5173`)
— **não um placeholder de produção inventado**. Antes de um deploy de
produção real, `CORS_ALLOWED_ORIGINS` precisa ser definida
explicitamente com a(s) origem(ns) real(is) do frontend hospedado —
a aplicação já falha ao subir sem isso, então este não é um gap
silencioso, é uma decisão que exige input do Criador quando o domínio
real existir.

### Parte B — Rate limiting no login

**Mecanismo escolhido: contador de janela fixa em Redis, chave por
(IP de origem, username tentado)** — reaproveita `settings.redis_url`
(o mesmo Redis já usado pela fila de dispatch), nenhuma infraestrutura
nova. Nenhuma biblioteca de rate limiting já estava em
`pyproject.toml` (confirmado por busca exaustiva na auditoria
anterior) — implementação própria, mínima (`app/auth/rate_limit.py`).

**Por que janela fixa, não janela deslizante**: a única fraqueza real
de janela fixa — uma rajada bem na fronteira de duas janelas pode
permitir até ~2x o limite configurado no pior caso — não importa nesta
escala (sistema de um único Criador, o objetivo é atrito contra
automação, não controle preciso de throughput). Janela deslizante
exigiria guardar um timestamp por tentativa em vez de um inteiro, sem
benefício real aqui.

**Decisão registrada — login bem-sucedido não conta contra o limite, E
limpa falhas anteriores**: `LoginRateLimiter.check()` roda antes da
tentativa real de login; `record_failure()` só é chamado se
`AuthService.login()` levantar `HTTPException`; `reset()` é chamado no
sucesso, apagando a chave inteira. Motivo: o objetivo é atrito contra
adivinhação automatizada, não punir um Criador legítimo que errou a
senha uma ou duas vezes antes de acertar — se um sucesso não limpasse
as falhas anteriores, algumas tentativas erradas ocasionais deixariam
o contador perigosamente perto do limite sem motivo real.

**Configuração**: `LOGIN_RATE_LIMIT_ATTEMPTS` (default 10),
`LOGIN_RATE_LIMIT_WINDOW_SECONDS` (default 60) — `app/config.py` +
`.env.example` (ambos).

**Resposta ao exceder**: HTTP 429, `detail="Too many login attempts"`
— sem contagem de tentativas nem tempo restante, nada que ajude um
atacante a calibrar.

### Testes reais
`ruff check` (todos os arquivos tocados): **All checks passed!**

**Parte A** (`tests/test_cors.py`, 5 testes): origem permitida recebe
`Access-Control-Allow-Origin`; origem não listada não recebe o header
para aquela origem; `Settings(app_env="production",
cors_allowed_origins=None, ...)` levanta `ValidationError` mencionando
`CORS_ALLOWED_ORIGINS`; produção aceita uma origem explícita
configurada; `"*"` nunca coexiste com `allow_credentials=True`
(testado com `["*"]`, `["origem-explícita"]`, e uma lista mista).
**5/5 passed**.

**Parte B** (`tests/test_login_rate_limit.py`, 3 testes, override de
dependency com `max_attempts=2, window_seconds=2` — documentado como
valor só de teste, não divergência silenciosa do default de produção):
N+1 tentativas erradas retornam 429 com mensagem genérica (sem
dígitos); a janela reseta de verdade depois de esperar
`window_seconds` reais (`asyncio.sleep`, não mockado) — tentativa
seguinte volta a ser 401 (credenciais erradas), não 429; login bem-
sucedido nunca conta contra o limite, e um sucesso depois de uma falha
limpa essa falha. **3/3 passed** (~26s, dominado pelo `sleep` real do
teste de reset).

Regressão: `tests/test_auth.py` (8) + `tests/test_cors.py` (5) +
`tests/test_login_rate_limit.py` (3) + `tests/test_http_integration.py`
(5) juntos, contra `postgres-test`: **21/21 passed**.

### Arquivos alterados/criados
**Parte A**: `backend/app/config.py`, `backend/app/main.py`,
`.env.example`, `backend/.env.example`, `backend/tests/test_cors.py`
(novo).
**Parte B**: `backend/app/auth/rate_limit.py` (novo),
`backend/app/auth/routes.py`, `backend/app/config.py`,
`.env.example`, `backend/.env.example`,
`backend/tests/test_login_rate_limit.py` (novo).

### Pendências reais
1. Origem real do frontend em produção não determinada — precisa de
   input do Criador quando o domínio existir; a aplicação já falha ao
   subir em produção sem `CORS_ALLOWED_ORIGINS` configurada, então não
   há risco de deploy silenciosamente permissivo.
2. `X-Forwarded-For`/proxy reverso não tratado no rate limiter —
   `http_request.client.host` reflete a conexão direta; se um proxy
   reverso for colocado na frente da API no futuro, o IP de origem
   real precisará ser lido de um header confiável configurado pelo
   proxy, não implementado aqui (não há proxy reverso neste projeto
   hoje).
3. Pendências já registradas na auditoria anterior e ainda não
   endereçadas: logging JSON estruturado inexistente como prática
   geral; métricas de observabilidade incompletas; `datetime.utcnow()`
   depreciado em `auth.py`.


## Lote: DEUS inicia conversa automaticamente após login (saudação contextual)

**Contexto.** Até este lote, DEUS nunca falava primeiro: o Criador só via
uma frase local fixa ("DEUS esta presente. Aguardando a palavra do
Criador.") até enviar a primeira mensagem — e nem sequer havia
persistência real da conversa entre recarregamentos de página (ver
achado de auditoria abaixo). Este lote faz o login autenticado gerar uma
mensagem de GOD real, persistida, resumindo o estado do sistema, sem
que o Criador precise perguntar.

**Achado de auditoria que mudou o escopo real do trabalho.** O prompt
original assumia que "GET /conversations/{id}/messages que o frontend já
chama" existia. Não existia: não havia rota de listagem de mensagens no
backend (`app/api/living_core.py` só tinha `POST .../messages`), e o
frontend nunca buscava histórico de conversa — `ensureConversation()`
criava uma Conversation nova (`title="Creator Interface"`) na primeira
mensagem enviada em cada sessão de navegador, e o estado `chat` local
nunca era persistido/recarregado (não fazia parte de `WorkspaceCache`).
Ou seja: todo reload de página já perdia o histórico de conversa
silenciosamente, independente deste lote. Em vez de forçar a saudação
para dentro dessa arquitetura efêmera, o lote resolveu a causa raiz:
- Backend: nova rota `GET /conversations/{entity_id}/messages`
  (`app/api/living_core.py`, `LivingCoreService.messages()`,
  `DomainRepository.list_messages()`) — extensão simétrica natural da
  `POST` que já existia, reaproveitando a mesma checagem de posse
  (`_owned`).
- Backend: `POST /auth/login` agora resolve/cria a "conversa âncora" do
  DEUS do Criador (`GodConversationRepository.anchor_conversation_id()`,
  título fixo `__deus_conversation__`) e retorna `conversation_id` em
  `TokenResponse` (campo novo, opcional — `refresh()` continua
  retornando `null` ali, sem nenhuma mudança de comportamento).
- Frontend: `App.tsx` agora cacheia esse `conversation_id` em
  `localStorage` (mesmo padrão já usado para `creator-token`), e um novo
  `useEffect` carrega a conversa e seu histórico real
  (`GET .../messages`) sempre que há token — login novo ou reload de
  página com token já salvo, sem diferença. Efeito colateral (bom,
  incidental, não pedido mas correto): a conversa com DEUS agora
  sobrevive a reloads de página, o que não era verdade antes deste lote.

**Conversa âncora vs. anchor de memória.** `__deus_conversation__`
(nova, para a conversa exibida) é deliberadamente distinta de
`__creator_memory__` (`CreatorRecallRepository`, já existente, guarda
`conversation_memory` para recall — não é a thread visível de chat).
Mesmo padrão get-or-create-por-título, propósitos diferentes.

**Idempotência: janela de tempo, não sessão de token.** Access tokens
são JWT stateless (`app/services/auth.py` não persiste sessão nenhuma),
então "primeira carga de uma sessão de token nova" não é algo que o
backend consiga observar diretamente sem adicionar um registro de
sessão novo — rejeitado por ser infraestrutura desproporcional ao
problema. Em vez disso: `maybe_send_login_greeting()`
(`app/services/greeting.py`) consulta a própria saudação mais recente já
persistida (`GodConversationRepository.latest_greeting_message()`,
via `Message.metadata_json->>'greeting' = true`) e só gera uma nova se
a última tiver mais de `LOGIN_GREETING_COOLDOWN = 30 minutos`. Não
requer coluna nova nem migração — dado real já existente é a própria
fonte da verdade. 30 minutos: mais longo que o access token (15 min,
`ACCESS_TOKEN_EXPIRE_MINUTES`) para não repetir a cada refresh de
página dentro da mesma sessão de trabalho; curto o suficiente para que
um retorno horas depois no mesmo dia ainda receba um resumo
genuinamente atual. `/auth/refresh` nunca chama esse mecanismo — só
`/auth/login`, conforme escopo do prompt.

**Conteúdo da saudação: reaproveitado, não reimplementado.**
`GodConversationService._system_snapshot()` e
`app.core.god._format_system_query_reply()` foram renomeados para
públicos (`system_snapshot()` / `format_system_query_reply()`) — mesma
lógica, agora com dois chamadores (o SYSTEM_QUERY já existente, e este
lote). A saudação chama `system_snapshot(actor, "estado do sistema")`
(dispara o tópico "general" do SYSTEM_QUERY, que já teria sido usado se
o Criador tivesse perguntado "qual o estado do sistema") e formata com
`format_system_query_reply()`, prefixando com
`"DEUS esta presente. Bem-vindo de volta, Criador. "`. Exemplo real
capturado em produção local (docker compose, ver ENTREGA FINAL): "DEUS
esta presente. Bem-vindo de volta, Criador. Estado geral: 0 missoes em
andamento, 1 Inceptions pendentes, 3 Universos ativos, 3 agentes
ativos."

**Pendências reais.**
1. `tests/test_login_rate_limit.py` (lote anterior, não deste lote) usa
   `TEST_WINDOW_SECONDS = 2` — sob esta máquina de desenvolvimento sob
   carga pesada (verificação de bcrypt chegando a 1.3–2.4s por
   requisição em vez dos ~50-200ms normais), o teste
   `test_exceeding_the_window_returns_429...` e
   `test_window_resets_automatically...` podem falhar de forma
   intermitente porque a janela de 2s do teste expira entre as
   tentativas antes da terceira chegar — reproduzido em isolamento
   (1 falha em uma execução, 0 falhas duas execuções seguintes depois),
   confirmando que é fragilidade de timing pré-existente do teste sob
   carga, não uma regressão deste lote (este lote não toca o caminho de
   falha de login, só o de sucesso, depois de `rate_limiter.reset()`).
   Não corrigido aqui — fora do escopo deste lote, sinalizado para
   ajuste futuro (aumentar `TEST_WINDOW_SECONDS` ou mockar tempo).
2. Complaint original do Criador ("painéis muito pequenos") permanece
   não investigado — fora do escopo deste lote, que tratou
   especificamente da saudação automática.


## Fix: atalhos do dock ("Mostrar Capabilities"/"Mostrar Auditoria") inclicaveis sob o rodape de Chronicles

**Contexto.** Reclamação do Criador ("painéis muito pequenos" / conversa
parecendo não funcionar) levou a uma investigação real via
`getBoundingClientRect()` em 1366×768, 1440×900 e 1920×1080 — não
reprodução por adivinhação. `.dock-shortcut-pills` usava
`flex-wrap: wrap`; com 7 atalhos e `width: min(720px, ...)`, eles sempre
quebravam em 2 linhas, em qualquer resolução testada. Como o contêiner é
`position: fixed; bottom: 38px` (borda inferior fixa, cresce para cima
conforme quebra linhas), a segunda linha (contendo justamente
"Mostrar Capabilities" e "Mostrar Auditoria") caía inteiramente dentro
da faixa ocupada por `.chronicle-ticker` (rodapé fixo, `z-index: 24` >
`dock-shortcut-pills`'s `z-index: 20`), tornando esses dois atalhos
100% inclicáveis por mouse, sempre — não uma falha rara de tela
pequena.

**Fix.** `flex-wrap: nowrap` + `overflow-x: auto` (mesmo padrão já usado
em `.chronicle-ticker-track` — reaproveitado, não inventado) mantém os
7 atalhos numa única linha, com rolagem horizontal se necessário, nunca
quebrando para uma segunda linha. Isso por si só não bastava: o
`bottom: 38px` original tinha sido calibrado para a LINHA DE CIMA de um
layout de 2 linhas — colapsar para 1 linha moveu o conteúdo para a
posição da linha de baixo (a perigosa). Recalibrado para `bottom: 80px`,
medido contra o espaço real livre entre `.conversation-dock` (borda
inferior em 792px, viewport 900px) e `.chronicle-ticker` (borda superior
em 823px) — um vão de apenas ~31px. A linha única de pills (26px de
altura) agora fica em [794px, 820px], com folga de verdade dos dois
lados. Confirmado via clique real em "Mostrar Auditoria" (antes 100%
falho) após o fix.

**Não corrigido nesta rodada:** o breakpoint mobile
(`@media (max-width: 760px)`) usa `bottom: 8px` para os mesmos pills,
não recalibrado — não há medições reais de mobile ainda, e o relato
original veio de uso desktop. Sinalizado como pendência real, não uma
correção silenciosa assumida como concluída.

**Fonte pequena nos painéis (9-10px) — não alterada.** É um padrão
tipográfico deliberado e disseminado por dezenas de regras no mesmo
arquivo (rótulos em caixa alta com letter-spacing largo, estética HUD já
estabelecida em "feat(interface): rebuild Creator Interface as a
living-universe dashboard" e reconciliada com "frozen spec" em commit
posterior). Reescrever isso em massa seria uma decisão de design
unilateral e de alto risco sobre uma spec já revisada — não fiz, e
reportei ao Criador como uma pergunta em aberto em vez de decidir
sozinho.
