# Auditoria v0.5 — Fase 1 (Consolidação)

Auditoria executada em 2026-07-19 contra o estado atual do repositório
(branch `fix/creator-interface-living-functional-scene`), com evidência real
de execução. Nenhuma correção foi aplicada nesta fase — apenas coleta de
evidência, conforme exigido pelo prompt de finalização.

Ambiente: Windows 10, Docker 29.6.1, Docker Compose v5.1.4, Python 3.14.4
(host), Postgres 16-alpine e Redis 7-alpine via `docker compose`.

---

## 1. Infraestrutura — evidência bruta

### `docker compose config`

Resolve sem erros. Confirma 4 serviços por padrão (`api`, `postgres`,
`redis`, `frontend`) e um quinto (`worker`) atrás do profile
`future-runtime`, que **não** aparece na resolução padrão — confirmando que
está desligado por default. Saída completa nos logs desta sessão; trecho
relevante:

```
name: thecreationos
services:
  api: ...        (depends_on postgres/redis healthy)
  frontend: ...    (depends_on api healthy)
  postgres:
    image: postgres:16-alpine
  redis:
    image: redis:7-alpine
    # nenhuma porta publicada por padrão
```

### `docker compose up --build` (banco vazio)

Volumes removidos deliberadamente (`docker compose down -v`) antes de subir,
para provar que a inicialização funciona do zero:

```
NAME                       STATUS
thecreationos-api-1        Up (healthy)
thecreationos-frontend-1   Up (healthy)
thecreationos-postgres-1   Up (healthy)
thecreationos-redis-1      Up (healthy)
```

Os 4 serviços padrão sobem saudáveis sem nenhum passo manual além do que já
existe (`.env` + `secrets/*.txt` já estavam presentes neste ambiente).

### Migrations em banco vazio

O `CMD` da imagem `api` já roda `python -m alembic upgrade head` antes do
`uvicorn` ([backend/Dockerfile:28](backend/Dockerfile#L28)). Log real contra
volume novo, sequencial e sem erro, de `0001_initial` até
`0021_mission_authorization` (21 migrações, cabeçalho confirmado por
`alembic current` = `0021_mission_authorization (head)`).

**Comando único documentado para aplicar migrations:** já existe implícito
no entrypoint do container; para rodar isoladamente:
`python -m alembic upgrade head` (dentro de `backend/`, com `DATABASE_URL`
setado).

### `pytest -v` completo (contra Postgres + Redis reais, não fakes)

Suíte completa: **323 testes coletados, 322 passaram, 1 falhou.**

```
=========== 1 failed, 322 passed, 2 warnings in 1009.48s (0:16:49) ============
FAILED tests/test_consolidation_integration.py::test_0009_migration_round_trip
```

Para rodar a suíte completa (não só `-m "not integration"`) foi necessário:
1. Criar um banco descartável `the_creation_os_test` no Postgres do compose
   (mesma instância, nome com marcador `test`, validado por
   `backend/tests/db_safety.py`).
2. Publicar a porta do Redis no host — **o `docker-compose.yml` não expõe
   `6379` por padrão**, só é alcançável dentro da rede `tco_net`. Usei um
   `docker-compose.override.yml` local (não versionado, adicionado ao
   `.gitignore`) só com `redis.ports: ["6379:6379"]` para o teste. Isso não
   é uma mudança de arquitetura, é infraestrutura de teste local.

**A única falha — causa raiz real, corrigida no Lote 2.1 (ver seção 6):**
`test_0009_migration_round_trip` falha em banco de teste recém-criado
porque `alembic downgrade` não tem uma revisão atual válida para partir
(sem `alembic_version`, um banco vazio não pode ser "rebaixado"). A
hipótese inicial registrada aqui na primeira passada desta auditoria —
atrito Windows/`asyncio` com `subprocess.run` — **estava errada** e foi
descartada com prova real: o mesmo teste, no mesmo banco vazio, falha
identicamente dentro de um container Linux (exit 255, não o código do
Windows). A causa real e a correção estão documentadas na seção 6.

---

## 2. FUNCIONA (comprovado por teste ou execução real)

- **Stack completa sobe saudável** — `api`, `postgres`, `redis`, `frontend`
  healthy, banco vazio → migrations → app pronta, sem intervenção manual.
- **Migrations**: 21 revisões aplicam limpo em sequência, para frente e
  para trás (downgrade provado manualmente).
- **322/323 testes passam**, incluindo integração real com Postgres/Redis
  via Docker (não só fakes em memória): auth, conversa/DEUS, SOPHIA,
  ROCKMAM, Trindade, Tree Core, Central Core, Dispatch, Execution state
  machine, Mission Authorization, Opportunities, Perception, Automation,
  Capabilities, Voice, Worker Protocol, GitHub connector.
- **Chronicles — cadeia de hash já implementada e correta**
  ([backend/app/repositories/domain.py:93-136](backend/app/repositories/domain.py#L93-L136)):
  `add_event` grava `payload_hash = sha256(canonical_json(evento) +
  previous_hash)`; `verify_chronicle()` reprocessa toda a cadeia
  recalculando hash e comparando, valida sequência de `position` sem
  buracos e linkagem de `previous_hash`. Usa `pg_advisory_xact_lock` para
  serializar o caso de cadeia vazia sob concorrência (testado em
  `test_postgres_integration.py` com 6 escritas concorrentes).
- **Teste de adulteração já existe e já passa**:
  `test_chronicle_verifier_detects_tampering`
  ([backend/tests/test_postgres_integration.py:174-186](backend/tests/test_postgres_integration.py#L174-L186))
  altera `payload_json` direto no banco via ORM e confirma
  `verify_chronicle().valid == False` com `reason == "invalid event hash"`.
- **Chronicles é append-only por omissão**: não existe nenhum método de
  update/delete em `DomainRepository` para `Chronicle`.
- **Sanitização de payload nas Chronicles**: função `sanitize()`
  ([backend/app/repositories/domain.py:18-26](backend/app/repositories/domain.py#L18-L26))
  remove `token`, `password`, `secret`, `authorization`, `cookie`,
  `api_key`, `access_token`, `refresh_token` do payload antes de gravar.
- **`GET /api/v1/pulse` já é real, não hardcoded**
  ([backend/app/api/creator_interface.py:72-125](backend/app/api/creator_interface.py#L72-L125)):
  testa `SELECT 1` no Postgres de verdade, `PING` no Redis de verdade com
  timeout, chama `verify_chronicle()`, conta universos/agentes ativos,
  missões em execução, inceptions/tasks pendentes e tasks falhadas. Só
  expõe classe da exceção (`exc.__class__.__name__`), nunca mensagem/
  stacktrace — não vaza segredo.
- **`GET /health/live` e `GET /health/ready`** existem e são a baseline de
  RC documentada.
- **Idempotência de decisão de Inception, muito provavelmente já correta**:
  a máquina de estados em `core/domain.py` só permite transições
  específicas a partir de `PROPOSED`; qualquer transição inválida levanta
  `InvalidStateTransition(DomainError)`, que o handler global em
  [backend/app/main.py:42-45](backend/app/main.py#L42-L45) converte
  automaticamente em HTTP 409. (Não testei uma segunda decisão via curl
  ainda — ver pendência abaixo.)
- **Abstração de embedding com fake determinístico já existe**:
  `FakeEmbeddingModel.embed()` ([backend/app/ai/fake.py](backend/app/ai/fake.py))
  é uma função pura determinística (mapeia caracteres para floats), pronta
  para uso em testes.
- **`.gitignore` já protegia `secrets/*` e `.env`** antes desta auditoria
  (confirmado com `git check-ignore -v`) — só o
  `docker-compose.override.yml` temporário precisou ser adicionado.
- **Módulos periféricos têm cobertura de teste real hoje**: `voice`,
  `opportunities` (+ `_http`), `perception` (+ `_http`), `automation`,
  `capabilities`, `capability_governance`, `capability_persistence` — todos
  passaram na suíte completa. Não estão "incompletos" no sentido do prompt;
  estão testados e funcionando no escopo atual.

## 3. EXISTE MAS NÃO FUNCIONA / INCOMPLETO

- **Execução automática ponta a ponta não existe.** `app/services/workers.py`
  não tem nenhum loop de consumo (`while True`, `asyncio.sleep`, polling —
  nenhum encontrado). O worker do `docker-compose.yml`
  (`command: ["python", "-m", "app.worker"]`) referencia um módulo
  **`app/worker.py` que não existe no repositório** — se o profile
  `future-runtime` fosse ativado hoje, o container quebraria no boot com
  `ModuleNotFoundError`. Dispatch/Execution existem como protocolo e
  endpoints manuais (v0.4.3/v0.4.4/v0.4.5), mas nada os aciona sozinho.
- **`GET /api/v1/chronicles/verify` não existe como endpoint HTTP
  dedicado.** A lógica (`verify_chronicle()`) já existe e já é usada
  internamente por `/pulse`, só falta expor a rota própria pedida no
  critério de aceitação.
- **Memória em 4 camadas — parcial e com nomenclatura diferente da
  pedida.** Existem 4 tabelas relacionadas a memória, mas em estados muito
  diferentes:
  - `CreatorMemory` ([backend/app/models/memory.py](backend/app/models/memory.py)):
    **completa** — repository, `MemoryService` (remember/search/context_for_god),
    testada.
  - `MissionMemory`, `UniverseMemory`, `ConsciousMemory`
    ([backend/app/models/entities.py:242-273](backend/app/models/entities.py#L242-L273)):
    **existem só como tabela** — zero repository, zero service, zero rota,
    zero teste, confirmados por busca no código inteiro.
  - `ConsciousMemory.embedding` é `JSON`, não uma coluna vetorial — não há
    busca por similaridade, só um campo solto.
  - O enum atual de tipo de memória (`EPISODIC/SEMANTIC/OPERATIONAL/CREATOR`
    em `core/memory.py`) não corresponde 1:1 à nomenclatura pedida
    (conversa/missão/universo/Conscious Memory) — é uma taxonomia diferente
    que já existe e funciona para `CreatorMemory`.
- **CORS hardcoded, não configurável**: `allow_origins=["*"]` fixo em
  [backend/app/main.py:19](backend/app/main.py#L19), sem leitura de env var.
- **Rate limiting de login: não encontrado em lugar nenhum do código.**

## 4. FALTANTE

- ~~pgvector: imagem `postgres:16-alpine`, sem `CREATE EXTENSION vector`~~ —
  **resolvido no Lote 2.1**, ver seção 6. A coluna `ConsciousMemory.embedding`
  continua `JSON` (tipo pgvector real fica para o Lote 2.5, por escopo).
- ~~Script/Makefile para gerar `secrets/*.txt`~~ — **resolvido no Lote 2.1**,
  ver seção 6.
- **Seed dos 12 Universos**: não existe script de seed em lugar nenhum do
  código (`app/db/initial.py` só imprime uma mensagem, não popula nada).
  As pastas `app/universes/engineering`, `app/universes/knowledge`,
  `app/universes/security` existem mas estão **vazias** — não há nenhum
  agente determinista por universo implementado no nível de arquivo, só a
  estrutura de diretório.
- **`app/pulse/`, `app/events/`, `app/constitution/` são diretórios
  vazios ou stubs** (`constitution/__init__.py` tem 0 bytes) — não
  correspondem a onde a lógica realmente vive hoje (que é
  `api/creator_interface.py`, `repositories/domain.py`,
  `models/entities.py`). Não é um bug funcional, mas é scaffolding morto
  que confunde quem procura Pulse/Chronicles pelo nome do diretório.

---

## 5. Observação sobre o escopo da Fase 2 em diante

Esta auditoria já muda a leitura do prompt original em pontos
importantes: Pulse, a cadeia de hash das Chronicles e a detecção de
adulteração **já existem e já passam em teste real** — não precisam ser
"implementados", só ganhar o endpoint `/chronicles/verify` dedicado. Por
outro lado, a lacuna mais séria e mais trabalhosa do pedido —
execução automática ponta a ponta (2.2) — está confirmada como
genuinamente ausente (nem o módulo do worker existe), e é a que mais
risco de regressão carrega se for feita apressada.

Dado o tamanho real do que falta (worker/executor real, pgvector,
3 camadas de memória para ligar de verdade, seed de 12 universos com
agentes reais por universo ativo, rate limiting, CORS configurável,
suíte de testes nova para cada item), meu plano é atacar a Fase 2 em
lotes verificáveis, um de cada vez, cada um terminando com teste real
rodado (não prometido) — e não tentar entregar tudo de uma vez sem
checkpoint.

---

## 6. Lote 2.1 — Infraestrutura (fechado)

### O que mudou

- `docker-compose.yml`: `postgres.image` trocado de `postgres:16-alpine`
  para `pgvector/pgvector:pg16`.
- Nova migration `backend/alembic/versions/0022_pgvector_extension.py`:
  `CREATE EXTENSION IF NOT EXISTS vector;` (upgrade) /
  `DROP EXTENSION IF EXISTS vector;` (downgrade).
- `backend/app/api/health.py`: `EXPECTED_ALEMBIC_REVISION` atualizado de
  `0021_mission_authorization` para `0022_pgvector_extension` — consequência
  obrigatória de avançar o head; sem isso `/health/ready` reportaria
  desalinhamento de schema permanentemente.
- Referências ao head em `README.md`, `backend/README.md`,
  `backend/MIGRATIONS.md`, `ARCHITECTURE.md`, `docs/RELEASE_CHECKLIST.md`
  atualizadas para `0022_pgvector_extension`.
- Novo `scripts/generate-secrets.ps1`: gera `app_secret_key.txt`,
  `creator_bootstrap_password.txt`, `postgres_password.txt` e
  `database_url.txt` (mesma senha) com bytes aleatórios
  criptograficamente seguros; cria vazios os três arquivos de integração
  opcional (`elevenlabs_api_key.txt`, `github_token.txt`,
  `llm_api_key.txt`) só se ainda não existirem. Idempotente por padrão;
  `-Force` para regenerar.
- `README.md`: seções "Environment" e "Docker Startup" reescritas com a
  sequência reproduzível completa (secrets → reset opcional → `up --build`
  → verificação de migration/extension).
- `.gitignore`: adicionado `docker-compose.override.yml` (usado localmente
  só para publicar a porta do Redis durante testes de integração — não faz
  parte da topologia de produção).
- `backend/tests/conftest.py`: nova fixture `_migrate_test_database_to_head`
  (session-scoped, autouse) — ver causa raiz abaixo.

### Prova do item 1 — reset completo do zero

Sequência real executada (não simulada):

```powershell
.\scripts\generate-secrets.ps1 -Force   # gera todos os secrets do zero
docker compose down -v                  # remove containers + volumes
docker compose up --build -d            # sobe com a imagem pgvector nova
docker compose ps
```

Resultado:

```
NAME                       IMAGE                    STATUS
thecreationos-api-1        thecreationos-api        Up (healthy)
thecreationos-frontend-1   thecreationos-frontend   Up (healthy)
thecreationos-postgres-1   pgvector/pgvector:pg16   Up (healthy)
thecreationos-redis-1      redis:7-alpine           Up (healthy)
```

```powershell
docker compose exec -T api python -m alembic current
# 0022_pgvector_extension (head)

docker compose exec -T postgres psql -U postgres -d the_creation_os -c "SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';"
#  extname | extversion
# ---------+------------
#  vector  | 0.8.5

Invoke-WebRequest http://127.0.0.1:8000/api/v1/health/ready
# {"status":"ready"}
```

Os 4 serviços padrão sobem saudáveis a partir de volume vazio sem nenhum
passo manual além de `.env` (copiado do example) e o script de secrets.
`generate-secrets.ps1` foi testado nos dois modos: geração real (`-Force`,
gravou os 4 arquivos obrigatórios com conteúdo novo) e idempotência (sem
`-Force`, todos os 7 arquivos ficaram "skip").

### Prova do item 2 — `test_0009_migration_round_trip`

**A hipótese registrada na primeira passada desta auditoria (atrito
Windows/`asyncio` com `subprocess.run`) estava errada.** Não aceitei minha
própria especulação como prova — reproduzi dentro de um container Linux
(`docker run` a partir da imagem `thecreationos-api`, na rede
`thecreationos_tco_net`, banco de teste igualmente vazio) e o teste falhou
**do mesmo jeito**, com `exit status 255` (não o código do Windows):

```
tests/test_consolidation_integration.py F....
FAILED tests/test_consolidation_integration.py::test_0009_migration_round_trip
1 failed, 4 passed, 2 warnings in 130.60s
```

Isso descartou a hipótese de plataforma. Investigando o estado real do
banco (`\dt`, `SELECT * FROM alembic_version`), a causa raiz é: **um
`TEST_DATABASE_URL` recém-criado não tem `alembic_version` até que algo
rode `alembic upgrade head` nele.** `test_0009_migration_round_trip` é o
primeiro teste do arquivo e começa chamando `alembic downgrade
0008_agent_execution` — sem uma revisão atual conhecida, esse downgrade não
tem de onde partir e falha imediatamente. Nos runs anteriores (completos),
isso não aparecia como problema visível porque o hook de teardown do
próprio `conftest.py` (`pytest_runtest_teardown`, que já existia e roda
`alembic upgrade head` depois de qualquer teste "migration_round_trip",
passe ou falhe) corrigia o schema a tempo dos testes seguintes — mascarando
a causa raiz atrás de "só esse teste falha, os outros passam".

**Correção**: nova fixture `_migrate_test_database_to_head` (session-scoped,
autouse) em `backend/tests/conftest.py`, simétrica ao teardown já existente,
rodando `alembic upgrade head` contra `TEST_DATABASE_URL` uma única vez
antes de qualquer teste da sessão.

Prova, banco de teste recriado vazio, mesmo container Linux:

```
tests/test_consolidation_integration.py .....
5 passed, 2 warnings in 118.19s
```

### Prova — suíte completa ao fechar o lote

Banco de teste recriado vazio mais uma vez; suíte completa no host
(Windows), não só os testes novos:

```
323 items collected
tests\test_consolidation_integration.py .....                            [ 15%]
... (todos os outros arquivos, sem F)
================ 323 passed, 2 warnings in 1268.94s (0:21:08) =================
```

**323 de 323 — zero falhas, zero skips.** `test_0009_migration_round_trip`
passa nas duas plataformas com a mesma correção; nenhum `skipif` foi
necessário porque a causa raiz não era de plataforma.

### Pendência aberta deste lote

`github_token.txt` e `llm_api_key.txt` continuam vazios por design (fake
providers). Isso está documentado em `secrets/README.md` e no comentário do
script, mas não há teste automatizado que trave esse comportamento como
intencional — se algum dia isso for um problema real, é um teste barato de
adicionar, não fiz porque não foi pedido neste lote.

### Pendências registradas pelo Criador (não bloqueiam)

- P1: `scripts/generate-secrets.sh` equivalente ao `.ps1`, para CI/Linux.
- P2: tokens vazios por design — já coberto acima.
- P3: se a suíte passar de ~30 min, separar com markers `unit`/`integration`.

---

## 7. Lote 2.2 — Nota de decisão (registrada antes do código)

### Worker separado (decisão já tomada, não reaberta)

`app/worker.py` roda como processo próprio, consumindo a dispatch queue
existente via o protocolo já congelado (v0.4.3 leasing por row lock +
tokens hash SHA-256; v0.4.4 claim → Execution Envelope). O worker é
**cliente** desse protocolo — nenhuma lógica de leasing, backoff, reclaim
de lease expirado ou hashing é reimplementada; tudo isso já existe em
`DispatchService`/`WorkerService` e já é testado
(`test_dispatch_service.py`, `test_worker_protocol.py`,
`test_execution_integration.py`). O worker chama esses métodos, não os
substitui.

### Investigação: dois achados que mudaram o desenho da cauda

1. **`MissionStatus` não tem `COMPLETED`.** O enum (`app/core/domain.py`)
   já define `AUTHORIZED → DISTRIBUTED → EXECUTING → MANIFESTED` como
   transições legais, mas nenhum código jamais as invoca. **Decisão:
   "Missão COMPLETED", para fins de aceite deste plano de finalização,
   é o `MANIFESTED` já existente.** Nenhum valor novo foi adicionado ao
   enum.
2. **Não existe orquestrador** encadeando consolidação → decisão →
   manifestação — cada serviço só é chamado pela própria rota HTTP
   Creator-autenticada, um de cada vez, manualmente, em todo teste
   existente.

### Onde a orquestração da cauda mora

Dentro de `app/worker.py`, disparada depois de cada execução bem-sucedida.
**A autoridade continua nos services existentes** — o worker só tenta, em
sequência, `ConsolidationService.consolidate()` →
`DecisionService.decide()` → `ManifestationService.manifest()`, todos já
idempotentes (traváveis por linha, "já existe? devolve sem duplicar").
Não pré-calculo "a missão está pronta" no worker — deixo
`build_consolidation()` (que já valida isso) recusar com
`ConsolidationError` quando ainda não está, e trato isso como "tentar de
novo depois", não como erro. Isso também resolve a retomabilidade exigida
pelo Guardrail 1: se o worker morrer no meio da cauda, a próxima tentativa
simplesmente encontra os registros já criados e continua do ponto seguinte
— nenhum dos três serviços precisa saber que houve uma queda.

### Mapa de transições e onde cada uma dispara

| Transição | Local | Disparo |
|---|---|---|
| `AUTHORIZED → DISTRIBUTED` | `DispatchService.enqueue` | primeiro `POST /dispatch` bem-sucedido para uma task da missão |
| `DISTRIBUTED → EXECUTING` | `DispatchService.lease` | primeiro `claim`/lease bem-sucedido de uma task da missão (mesmo caminho para rota manual `/dispatch/lease` e para `/workers/claim`) |
| `EXECUTING → FAILED` | `DispatchService.fail` | quando uma task esgota `max_attempts` e vai a `dead_lettered` |
| `EXECUTING → MANIFESTED` | `ManifestationService.manifest` | ao final da cauda (consolidação → decisão → manifestação aprovada) |

Todas usam o mesmo padrão: `mission(mission_id, lock=True)` (row lock já
existente nos três repositórios da cauda; adicionado em
`DispatchRepository`) + comparação "já está no alvo? não faz nada" antes
de chamar `transition()`. Isso é a trava atômica do Guardrail 1 — quem
perde a corrida vê o status já no valor de destino e simplesmente não
levanta erro. Cada transição efetivada emite um Chronicle
(`mission_distributed`, `mission_executing`, `mission_failed`,
`mission_manifested`).

### Guardrail 4 — bloqueio de missão FAILED/CANCELLED

`app/core/domain.py` já tinha `require_malkuth_authorized(status)`,
declarada mas **nunca chamada** — verifica exatamente
`status in {AUTHORIZED, DISTRIBUTED, EXECUTING}`. Reaproveitada (não
reescrita) como guarda em `consolidate`/`decide`/`manifest`, **depois** do
retorno idempotente (não antes — ver "achado durante a implementação"
abaixo): um registro que já existe é sempre devolvido, mas nenhum
trabalho novo começa para uma missão `FAILED`/`CANCELLED`.

### Credencial do worker

`app/admin/worker.py` espelha `app/admin/creator.py` linha a linha:
bootstrap idempotente rodado no startup da API (mesmo gate
`APP_ENV == "development"` do bootstrap do Creator), lendo o texto puro de
`/run/secrets/worker_credential` (novo secret, mesmo padrão
`*_FILE` de `config.py`), gravando só o hash SHA-256 (reaproveitando
`credential_hash()` de `app/services/workers.py`) no `Worker` de UUID fixo
e bem-conhecido. O mesmo bootstrap garante a existência da capability
`planning` (a única hoje com handler registrado, `structured_echo`) — sem
isso o worker não teria com o que se registrar. Nenhuma rota pública de
registro foi criada; nenhuma credencial em variável de ambiente versionada.
`scripts/generate-secrets.ps1` passa a gerar `worker_credential.txt`.

### O que este lote não inclui

Seed de universos/agentes (Lote 2.6) fica fora — para a prova E2E, o
agente com a capability `planning` é criado via curl usando as rotas
administrativas que **já existem** (`POST /capabilities`, `POST /agents`),
não por um script de seed novo.

---

## 8. Lote 2.2 — Fechamento e provas

### Dois achados durante a implementação, corrigidos na hora (mesmo padrão do Lote 2.1: reproduzir, não supor)

**1. `mission.status != "authorized"` estava hardcoded em quatro lugares
diferentes**, todos assumindo que a missão nunca sairia de `AUTHORIZED`
enquanto durasse a execução — o que deixou de ser verdade no momento em
que as transições `DISTRIBUTED`/`EXECUTING` passaram a ser reais.
Encontrados só porque os testes existentes começaram a falhar de verdade
ao rodar contra o fluxo automatizado:

- `app/core/consolidation.py` (`build_consolidation`)
- `app/services/execution.py` (`AgentExecutionService._chain`)
- `app/services/tree_core.py` (`TreeCoreService.match`, usado por
  `DispatchService.enqueue` para casar capability→agente)
- `app/services/planner.py` (`PlannerService._mission`)

Todos os quatro foram alargados para `{"authorized", "distributed",
"executing"}` — o mesmo conjunto que `require_malkuth_authorized` já usava.
Nenhum texto de erro de teste dependia do valor antigo (conferido antes de
alterar).

**2. `require_malkuth_authorized` na ordem errada quebrava o retorno
idempotente.** Primeira versão do código chamava a guarda **antes** do
"já existe? devolve" — o que rejeitava com 403 uma segunda chamada de
`/malkuth/.../manifest` depois que a missão já tinha virado `manifested`
(status fora do conjunto permitido, mas por ter *tido sucesso*, não por
estar falha). Corrigido invertendo a ordem nos três serviços da cauda:
idempotência primeiro, guarda só quando for iniciar trabalho novo. Prova:
`test_http_manifestation_idempotency_security_and_get_without_creation`
(já existia, pegou o bug de verdade).

### Dois gaps adicionais, também "existiam mas nunca eram chamados"

- **`GET /api/v1/chronicles/verify` não existia como rota.** A lógica
  (`DomainRepository.verify_chronicle()`) e até o schema de resposta
  (`ChronicleVerifyResponse`) já existiam, prontos, sem endpoint. Faltava
  literalmente a rota — adicionada em `app/api/creator_interface.py`.
- **`app/core/task_graph.py` já tinha `transition_task()`** validando a
  transição `CREATED/PLANNED → READY`, mas nenhum código a chamava —
  nada no sistema jamais tirava uma Task de `planned` para `ready`, o
  que teria bloqueado `DispatchService.enqueue` (exige `task.state ==
  "ready"`) para qualquer missão real. Novo
  `PlannerService.mark_ready()` + `POST /tasks/{id}/ready` ligam essa
  transição já existente, verificando que as dependências da task (se
  houver) já estão `completed` — mesma regra que `DispatchService.enqueue`
  já verificava separadamente.

Nenhum dos dois exigiu inventar lógica nova: os dois eram peças já
desenhadas no código, só nunca conectadas a uma rota.

### Um erro de infraestrutura próprio, também corrigido

Ao ligar `worker.capabilities` em `app/admin/worker.py` (bootstrap),
a query inicial não usava `selectinload` — acessar a relação depois
disparava `sqlalchemy.exc.MissingGreenlet` e derrubava a API inteira no
boot. Corrigido copiando o padrão já usado em
`app/repositories/workers.py` (`select(Worker).options(selectinload(...))`).
Pego porque testei a subida real do container, não só os testes unitários.

### Prova 1 — `docker compose up --build`, worker saudável por padrão

```powershell
docker compose down -v
docker compose up --build -d
docker compose ps
```

```
NAME                       STATUS
thecreationos-api-1        Up (healthy)
thecreationos-frontend-1   Up (healthy)
thecreationos-postgres-1   Up (healthy)
thecreationos-redis-1      Up (healthy)
thecreationos-worker-1     Up (healthy)
```

`docker compose logs api`: `{"restored": true, "reason":
"configured_creator_updated"}` / `{"restored": true, "reason":
"system_worker_credential_updated"}`. `docker compose logs worker`:
`authenticated as worker 00000000-0000-0000-0000-000000000001
(system-worker)`. Sem `--profile future-runtime` — o worker sobe por
padrão, como exigido.

### Prova 2 — transcript E2E real via curl, sem intervenção manual no banco

Sequência real (`curl.exe`, corpos via arquivo por causa de um bug de
escaping de aspas do PowerShell 5.1 com JSON inline — não é substituto,
é o mesmo `curl.exe`, só evitando um problema de shell conhecido):

```
1.  POST /auth/login                                    → access_token
2.  POST /conversations                                 → conversation
    POST /conversations/{id}/messages                   → message
3.  POST /inceptions                                     → status "proposed"
    POST /inceptions/{id}/submit
4.  POST /inceptions/{id}/approve                        → status "approved"
5.  POST /missions                                        → status "drafted"
    POST /missions/{id}/plan
    POST /missions/{id}/validate
    POST /missions/{id}/authorize                        → status "authorized"
6.  GET  /capabilities                                    → "planning" (criada pelo bootstrap do worker)
    POST /agents + /agents/{id}/capabilities + /heartbeat → agente "idle"
7.  POST /tasks                                            → task "created"
    POST /tasks/{id}/ready                                 → task "ready"
8.  POST /dispatch                                          → mission "authorized" → "distributed"
9.  polling GET /missions/{id} a cada 2s:
      [0] mission.status = executing
      [1] mission.status = manifested
11. GET /tree-core/missions/{id}/consolidation  → status "complete", fingerprint real
    GET /central-core/missions/{id}/decision    → decision "APPROVED"
    GET /malkuth/missions/{id}/manifestation    → manifestation_state "MANIFESTED"
12. GET /chronicles/verify                       → {"valid":true,"message":"Chronicle chain verified with no adulteration detected."}
```

**Do `POST /dispatch` até `mission.status == "manifested"`: ~4 segundos,
2 ciclos de polling, zero SQL manual, zero intervenção no banco.** O
worker reclamou o item, executou via `structured_echo`, e a própria
execução disparou consolidação → decisão → manifestação em cascata.

### Testes novos (`tests/test_worker_orchestration.py`, 5 testes)

- `test_enqueue_distributes_and_first_claim_executes_the_mission` —
  Guardrail 3: as duas transições certas, nos pontos certos, com Chronicle.
- `test_definitive_task_failure_fails_the_mission` — Guardrail 4:
  `max_attempts` esgotado → `dead_lettered` → Mission `FAILED`, atômico,
  sem erro pro chamador.
- `test_tail_orchestration_never_runs_for_a_failed_mission` — Guardrail 4:
  `consolidate`/`decide`/`manifest` recusam os três, nenhum registro criado.
- `test_concurrent_orchestration_produces_exactly_one_record_each` —
  Guardrail 1: 5 chamadas concorrentes de `consolidate→decide→manifest`
  na mesma missão, exatamente 1 registro de cada, status final
  `manifested` uma vez só.
- `test_manual_route_stays_idempotent_during_automatic_orchestration` —
  Guardrail 2: rota HTTP do Criador e chamada direta do worker intercaladas
  na mesma missão, nunca mais de 1 `MissionConsolidation`, toda resposta
  200 ou 201, nunca conflito.

### `pytest -v` completo, suíte inteira

Suíte completa: **328 testes coletados, 328 passaram, 0 falharam.**

```
=============== 328 passed, 4 warnings in 40307.02s (11:11:47) ================
```

Nota honesta sobre o caminho até aqui: a primeira execução completa (328
testes coletados) veio com **6 falhas**, todas em
`tests/test_tree_core.py::test_match_rejects_every_non_authorized_mission`
(parametrizado sobre `drafted/planned/validated/cancelled/failed/manifested`):

```
E       AssertionError: Regex pattern did not match.
E         Expected regex: 'authorized Missions'
E         Actual message: 'Tree Core only matches authorized, distributed, or executing Missions'
```

Root cause: ao ampliar a checagem de status em `TreeCoreService.match()`
(Guardrail para aceitar Missões `authorized`/`distributed`/`executing`, não
só `authorized`), a mensagem de erro mudou de "...authorized Missions" para
"...authorized, distributed, or executing Missions". O teste ainda estava
correto em sua intenção — todos os 6 estados testados continuam
corretamente rejeitados pela lógica nova, nenhum deles pertence ao conjunto
ampliado — só a substring buscada pelo `match=` do `pytest.raises` ficou
desatualizada. Corrigido atualizando o regex esperado em
`backend/tests/test_tree_core.py:168` para o texto real da nova mensagem;
nenhuma asserção foi enfraquecida ou removida. Reexecutada a suíte inteira
do zero (banco de teste dropado e recriado antes da segunda rodada) e
confirmado 328/328 verde.

### Pendências verdadeiras deste lote

- **Retry/backoff do worker**: o backoff exponencial já existe em
  `DispatchService.fail` (reaproveitado, não meu) e é coberto por
  `test_dispatch_service.py`. Não escrevi um teste adicional
  específico simulando múltiplas falhas transitórias seguidas de sucesso
  via o loop real do `app/worker.py` — testei a lógica de fail/retry no
  nível de serviço (já existente) e a falha definitiva → FAILED no nível
  de integração (novo). O caminho "falha, tenta de novo, sucede" ponta a
  ponta pelo processo do worker real não tem teste automatizado dedicado.
- **Reclaim de lease expirado**: a lógica já existe e é testada
  (`test_dispatch_service.py`), mas não escrevi um teste específico do
  cenário "worker A trava, lease expira, worker B reclama, worker A tenta
  agir depois com token velho e é rejeitado" no nível de integração — só
  no nível de serviço com fake repo.
- **Handler único**: `structured_echo` é o único handler registrado
  (política v0.4.5 exige determinístico + sem efeito colateral). A prova
  E2E é uma execução real desse handler, não uma simulação.

---

## 9. Aceite do Criador — Lote 2.2 e 2.3 fechados; punch-list aberto

Lote 2.2 aceito e fechado. Lote 2.3 (Chronicles) considerado fechado
junto — a única pendência era a rota `/verify`, resolvida no Lote 2.2;
sem trabalho adicional necessário a menos que auditoria futura revele
algo novo. Wall-clock anômalo da suíte (40307s) aceito como hibernação
da máquina, não investigado further; se reincidir em lote futuro,
investigar antes de atribuir à mesma causa.

### Punch-list (não bloqueia lotes seguintes, rastreado até fechar com prova)

- **P4**: teste de integração real (banco real, timing real de expiração
  de lease, não repo fake) com dois workers concorrentes disputando o
  mesmo lease expirado, provando reclaim sem dupla execução.
- **P5**: retry/backoff provado com o processo real do worker (não só
  nível de serviço): falha → retry → sucesso, ponta a ponta.
- **P6**: `structured_echo` como único handler — a ser resolvido pelo
  Lote 2.6 (agentes reais por Universo), fechando com um transcript E2E
  que use um handler real.

P4/P5/P6 só podem ser marcados como fechados com prova de execução real,
igual a todo o resto deste documento.

---

## 10. Lote 2.6 — Nota de decisão (registrada antes do código)

### Mapa do estado atual (auditoria, sem alterações)

- **`Universe`** (`app/models/entities.py:174-183`): tabela `universes` já
  existe (`id`, `code` unique, `name`, `active` bool, `created_at`).
  **Nenhuma migration ou seed jamais inseriu uma linha** — confirmado por
  grep em todas as 22 migrations e em `app/db/initial.py` (só imprime uma
  mensagem). `GET /api/v1/universes` já existe
  (`app/api/creator_interface.py:77-80`) e `/pulse` já conta
  `active_universes` — ambos esperando dados que nunca existiram.
- **Pastas `app/universes/{engineering,knowledge,security}`**: vazias,
  nem `__init__.py` — não são nem pacotes Python importáveis hoje. Não
  viram módulos novos neste lote: os 3 handlers deterministas são
  funções adicionadas a `app/agents/handlers.py` (arquivo já existente,
  já é onde `structured_echo` vive), não um `core/<universo>.py` novo.
- **`Agent`** (`entities.py:186-220`): tem **dois** campos de universo —
  `universe_name` (coluna física `universe`, string livre, sempre
  preenchida, é o que `register_agent()` usa hoje) e `universe_id` (FK
  para `universes.id`, existe na tabela desde a migration `0004`, **nunca
  preenchido por nenhum service atual**). Mesma situação em `Task`
  (`entities.py:136`): `universe_id` existe, nunca usado.
- **Elegibilidade hoje** (`TreeCoreRepository.eligible_agents()`,
  `app/repositories/tree_core.py:48-66`): filtra por
  `enabled/status=idle/heartbeat recente/tem todas as capabilities` — **não
  toca `Universe.active`** em lugar nenhum. Único ponto do sistema que
  decide "que Agent pode pegar essa Task" (chamado por
  `TreeCoreService.match()`, chamado por `DispatchService.enqueue()`).
- **Handler Registry** (`app/agents/handlers.py`, 106 linhas): contrato já
  documentado em `docs/AGENTS_V045_AUDIT.md` — `HandlerDefinition`
  exige `deterministic=True`, `side_effect_policy="none"`,
  `timeout_seconds>=1`; `ExecutionContext` não carrega sessão de banco,
  credencial, nem I/O; resolução é por `(name, version, capability)`,
  `capability` deve casar com um `Capability.name` existente. Único
  handler hoje: `structured_echo`/`1.0`/capability `planning`.
- **Acoplamento real encontrado no worker**: `app/worker.py:47-48`
  hardcoda `HANDLER_NAME="structured_echo"`/`HANDLER_VERSION="1.0"` e usa
  esse par **para toda e qualquer capability**, embora `_claim()`
  (linha 94) já devolva `capability_name` do item — hoje descartado
  (`_capability_name`). Sem corrigir isso, os 3 handlers novos nunca
  seriam de fato executados pelo worker automático, só via chamada
  direta de serviço em teste. Esse é o gap real que fecha o P6 do
  punch-list.
- **`Worker.capabilities`** (não confundir com `Agent`): o bootstrap do
  worker (`app/admin/worker.py`) hoje só registra a capability
  `planning` no único Worker do sistema (`SYSTEM_WORKER_UUID`).
  `WorkerService.claim()` restringe o `lease()` às capability_ids do
  próprio Worker (`services/workers.py:89`) — então, com uma capability
  nova sem estar na lista do Worker, nenhuma Task dessa capability jamais
  seria arrematada, mesmo com Agent e handler corretos.
- **`Task.input_json`**: coluna existe (`entities.py:149`), sempre `{}`
  hoje porque `TaskCreate` (schema) não tem esse campo e
  `PlannerService._new_task()` o hardcoda. Sem abrir esse campo, os 3
  handlers novos só poderiam ser exercitados com payload vazio — prova
  E2E fraca demais para alegar "handler real" (P6).
- **Padrão de referência (Trindade)**: `app/core/{god,sophia,rockmam}.py`
  = função pura determinística → `app/schemas/*.py` = resposta Pydantic
  tipada → `app/services/trinity.py` = idempotência/persistência/Chronicle.
  Não é o padrão que os 3 handlers seguem 1:1 (eles não persistem nada,
  não têm serviço de orquestração próprio — são funções puras dentro do
  Handler Registry, que já tem sua própria validação de schema de
  entrada/saída via Pydantic). O que é reaproveitado do padrão Trindade é
  só a ideia central: função pura, determinística, saída Pydantic tipada.
- **Teste de elegibilidade por Universo**: confirmado, **não existe**
  hoje em nenhum arquivo de teste (busca exaustiva em `backend/tests/`).
  Território novo, mas plugado no ponto de elegibilidade já existente
  (não duplicado).
- **`SecurityReviewAgent` — checagem de segredo reaproveitada**: o
  projeto já tem `SENSITIVE_KEYS`/`sanitize()` em
  `app/repositories/domain.py:18-26`, usado para sanitizar payloads de
  Chronicle antes de gravar. O handler de segurança reaproveita esse
  mesmo conjunto de chaves para avaliar exposição de segredo — não
  inventa uma lista nova.

### Decisões tomadas

1. **Seed dos 12 Universos + 3 Capabilities + 3 Agents via migration
   Alembic** (`0023_universe_agent_seed`, revisa `0022_pgvector_extension`),
   não via bootstrap-on-startup. Motivo: são dados de referência estáticos,
   sem segredo envolvido (diferente da credencial do worker) — uma
   migration é o mecanismo que o projeto já usa para isso, já roda
   automaticamente em todo boot (`alembic upgrade head` no `CMD` do
   Dockerfile), e independe de `APP_ENV=development` (diferente do
   bootstrap do worker/creator, que só roda em dev). Idempotente via
   `INSERT ... ON CONFLICT DO NOTHING` com parâmetros bindados (não
   f-string) em todas as 4 tabelas. IDs estáticos (mesmo padrão já usado
   para `SYSTEM_WORKER_UUID`), para que `downgrade()` seja simétrico.
   - Ativos: `knowledge`/Conhecimento, `engineering`/Engenharia,
     `security`/Segurança — códigos batendo com as 3 pastas já
     existentes em `app/universes/`.
   - Inativos (9): `vision`/Visão, `design`/Design, `business`/Negócios,
     `marketing`/Marketing, `legal`/Jurídico, `finance`/Finanças,
     `automation`/Automação, `communication`/Comunicação,
     `evolution`/Evolução. Só registro (código/nome/`active=false`) —
     nenhuma pasta, lógica ou handler para eles, por design (fora de
     escopo, conforme item 5 do pedido do Criador).

2. **Elegibilidade por Universo ativo é decidida em
   `TreeCoreRepository.eligible_agents()`**, estendendo o único filtro
   agregado que já existe, com `LEFT JOIN Universe` + `OR(Agent.universe_id
   IS NULL, Universe.active IS TRUE)`. **Não** em `Task.universe_id`
   (que fica não utilizado, como já estava — não é necessário para
   satisfazer "task para Universo inativo é rejeitada", e adicioná-lo
   seria escopo além do pedido). O `OR ... IS NULL` é obrigatório para
   não quebrar nenhum dos 328 testes/fixtures existentes que registram
   Agents com `universe` livre (ex.: `"central"`, `"test"`) nunca ligados
   a uma linha real de `Universe` — esses continuam elegíveis exatamente
   como hoje. A regra "Universo inativo nunca recebe task" vale apenas
   para Agents efetivamente ligados a um dos 12 Universos via
   `universe_id` — que passa a ser preenchido por `register_agent()`
   quando a string `universe` recebida casa com um `Universe.code`
   existente (case-insensitive), mantendo 100% de compatibilidade
   retroativa para qualquer outra string.

3. **`app/worker.py` para de hardcodar `structured_echo`.**
   `HandlerRegistry` ganha um método novo, `resolve_by_capability()`
   (extensão da classe já existente, não módulo novo), que devolve a
   `HandlerDefinition` cujo `.capability` casa com a capability do item
   arrematado. `_execute()` usa isso para escolher `handler_name`/
   `handler_version` por capability, em vez do par fixo. Corrige o gap
   real que impediria os 3 handlers novos de rodarem automaticamente
   pelo worker (não só em teste de serviço direto).

4. **`admin/worker.py` bootstrapa as 4 capabilities no único Worker do
   sistema**, não só `planning` — do contrário, `WorkerService.claim()`
   nunca arremataria nenhuma Task das 3 capabilities novas
   (`services/workers.py:89`, lease restrito às capability_ids do
   Worker). Get-or-create idempotente igual ao padrão já usado para
   `planning`.

5. **`Task.input_json` é aberto na API** (`TaskCreate.input_json: dict =
   {}`, opcional, passa por `create_task`/`_new_task` sem quebrar nenhum
   chamador existente — coluna já existia, só nunca exposta). Necessário
   para a prova E2E poder de fato mandar um payload não-trivial
   (`topic`/`requirements`/`subject`) para um dos 3 handlers novos —
   sem isso, "handler real" seria só `structured_echo` disfarçado
   recebendo `{}`.

6. **Os 3 handlers vivem como funções puras dentro de
   `app/agents/handlers.py`** (mesmo arquivo de `structured_echo`), cada
   um com `input_schema`/`output_schema` Pydantic próprios — o
   `output_schema` de cada um é uma subclasse de `StructuredResult` com
   `output` tipado (não `dict` genérico), mantendo compatibilidade total
   com `HandlerRegistry.invoke()` (que revalida contra `StructuredResult`
   via `.model_dump()` depois de validar contra o schema específico —
   nenhuma mudança necessária em `invoke()`). Nenhum handler faz I/O,
   randomização ou lê relógio — cada um é uma função determinística do
   seu próprio payload de entrada (e, no caso do `SecurityReviewAgent`,
   de `SENSITIVE_KEYS` importado, não inventado).

Escopo confirmado (Guardrails equivalentes aos do Lote 2.2): migration
`0023_universe_agent_seed.py`; `app/agents/handlers.py` (3 handlers +
`resolve_by_capability`); `app/worker.py` (usa a capability já
retornada por `_claim()`); `app/admin/worker.py` (lista de capabilities
do bootstrap); `app/repositories/tree_core.py` (`eligible_agents`);
`app/services/tree_core.py` (`register_agent` resolve `universe_id`
quando aplicável); `app/schemas/planner.py` + `app/services/planner.py`
(`input_json` opcional); testes novos. Nada além disso — nenhuma rota
nova, nenhum módulo novo, os 9 Universos inativos ficam só como registro.

### Achado real durante a subida do container (mesmo padrão do Lote 2.2)

`app/api/health.py:12` tinha `EXPECTED_ALEMBIC_REVISION =
"0022_pgvector_extension"` hardcoded — `/health/ready` (usado pelo
healthcheck do `docker-compose.yml`) comparava a revisão aplicada contra
essa constante e falhava (503) assim que a migration `0023` (nova,
deste lote) era aplicada, porque a revisão real deixou de bater com a
esperada. Corrigido para `"0023_universe_agent_seed"`. Pego só porque
testei a subida real do container (`docker compose up --build`), não só
os testes unitários — exatamente o mesmo tipo de achado do
`MissingGreenlet` do Lote 2.2. Nenhum teste referenciava essa constante,
então nada mais quebrou.

### Segundo achado real: `GET /agents/executions` nunca foi alcançável

Ao montar o transcript E2E deste lote (item 4 da prova exigida), a
chamada real `GET /api/v1/agents/executions` devolvia 422
(`"uuid_parsing"`, tentando validar `"executions"` como UUID) em vez da
lista de execuções. Causa: `app/api/__init__.py` registrava
`tree_core_router` (dono de `GET /agents/{agent_id}`) **antes** de
`execution_router` (prefixo `/agents/executions`) — o segmento dinâmico
único de `/agents/{agent_id}` intercepta `/agents/executions` primeiro
na ordem de resolução de rotas do FastAPI/Starlette. Corrigido invertendo
a ordem de registro em `app/api/__init__.py` (`execution_router` antes
de `tree_core_router`) — nenhuma rota mudou de lugar, só a ordem de
inclusão.

**O bug estava mascarado por uma asserção fraca já existente**:
`test_execution_integration.py` já chamava esse endpoint
(`assert len((await client.get("/api/v1/agents/executions", headers=creator)).json()) == 1`)
— mas `len(...)` aplicado a um corpo de erro `{"detail": [...]}` (uma
chave) também dá `1`, coincidindo com "uma execução na lista" (o
resultado correto). A asserção nunca distinguia os dois casos, então a
suíte ficava verde mesmo com a rota quebrada. Corrigido para verificar
`status_code == 200`, `isinstance(..., list)` e o `id` da execução
retornada — sem remover nenhuma cobertura existente, só fechando o
buraco. Achado só porque a prova E2E deste lote de fato chamou o
endpoint via HTTP real, não só via teste com corpo mockado.

---

## 13. Finalização v1.0.0-rc1 — segunda execução real, do zero, achado e corrigido em campo

Executado em 2026-07-21/22, a pedido explícito do Criador para repetir a
seção 3 de `docs/RELEASE_CHECKLIST.md` do zero, sem reaproveitar nenhuma
conclusão da seção 12 (que parava em `0023_universe_agent_seed` e não
sabia da migration `0024_creator_singleton`, ver 13.1). Docker Desktop,
Postgres/Redis reais, pytest real — nenhum resultado simulado.

### 13.1 Achado real no início da sessão: edição concorrente no mesmo repositório

Entre duas leituras do mesmo arquivo (`docs/RELEASE_CHECKLIST.md`),
minutos de intervalo, sem nenhuma edição feita por esta sessão, o
conteúdo mudou de referenciar `0023_universe_agent_seed` para
`0024_creator_singleton` nas mesmas linhas. Investigado antes de
continuar (não presumido): `git status`/`stat` confirmaram uma migration
nova, `backend/alembic/versions/0024_creator_singleton.py`, criada às
21:24 (não rastreada pelo git), e `backend/app/api/health.py`,
`README.md`, `ARCHITECTURE.md`, `backend/README.md`,
`backend/MIGRATIONS.md` e `docs/RELEASE_CHECKLIST.md` atualizados para
referenciá-la, tudo isso depois do início desta sessão. O repositório
vive dentro do OneDrive (`OneDrive.exe`/`OneDrive.Sync.Service.exe`
ativos) — a explicação mais provável é sincronização ao vivo de outra
sessão/dispositivo trabalhando no mesmo diretório. Reportado ao Criador
em tempo real; instrução recebida foi continuar e validar contra o
estado corrente, tratando `0024_creator_singleton` como o alvo real —
não `0023`, que a seção 12 deste documento ainda usava.

A migration `0024_creator_singleton.py` foi lida por inteiro antes de
prosseguir: implementa a Regra 1 da constituição ("Somente o Criador
possui controle total sobre GOD") no nível do banco — coluna
`creator.singleton` com `CHECK (singleton IS TRUE)` +
`UNIQUE (singleton)`, fechando uma corrida real em
`AuthService.bootstrap()` (check-then-insert sem lock, duas chamadas
concorrentes com usernames diferentes podiam criar dois Creators). Dentro
do escopo autorizado (hardening de segurança, não feature nova).
`backend/tests/test_auth.py` (novo, também não rastreado) já cobria a
migration e a corrida com `asyncio.gather` real — lido e confirmado
correto antes de aceitar `0024` como alvo.

### 13.2 Sequência real executada (seção 3 da checklist, do zero)

```powershell
docker version                          # engine hung ~15s no início (client
                                         # respondia, server não — mesmo padrão
                                         # já registrado na seção 12.2); resolvido
                                         # sozinho, sem reiniciar o Docker Desktop
docker compose config                   # resolve sem erro, 5 serviços (worker
                                         # incluído por padrão)
docker compose build                    # api, frontend, worker — 3 imagens OK
docker compose up -d --force-recreate
docker compose ps
```

```
NAME                       STATUS
thecreationos-api-1        Up (healthy)
thecreationos-frontend-1   Up (healthy)
thecreationos-postgres-1   Up (healthy)
thecreationos-redis-1      Up (healthy)
thecreationos-worker-1     Up (healthy)
```

```
GET /api/v1/health/live  → {"status":"live"}
GET /api/v1/health/ready → {"status":"ready"}
docker exec ... psql ... "SELECT version_num FROM alembic_version;"
  → 0024_creator_singleton   (bate com EXPECTED_ALEMBIC_REVISION atual)
```

Banco de teste descartável recriado do zero duas vezes nesta sessão
(antes e depois da correção da seção 13.3):

```powershell
docker exec thecreationos-postgres-1 psql -U postgres -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='the_creation_os_test' AND pid <> pg_backend_pid();"
docker exec thecreationos-postgres-1 dropdb -U postgres the_creation_os_test
docker exec thecreationos-postgres-1 createdb -U postgres the_creation_os_test
```

`python -m ruff check backend` → `All checks passed!` (limpo, antes e
depois das correções da seção 13.3).

Frontend (`frontend/`): `npm run test` → **2 arquivos, 15/15 testes
passaram**. `npm run build` (`tsc --noEmit && vite build`) → passou,
bundle de produção gerado (`dist/`), confirmado fora do controle de
versão (`git check-ignore -v frontend/dist` → ignorado por
`.gitignore:22`).

### 13.3 Falha real encontrada e corrigida: `creator.singleton` quebrou 16 testes de integração pré-existentes

Primeira rodada completa de `pytest backend/tests -q` contra o banco de
teste recém-criado: **16 erros reais** (não falhas de asserção — erros
de setup), todos com a mesma causa:

```
sqlalchemy.exc.IntegrityError: ... UniqueViolationError: duplicate key
value violates unique constraint "uq_creator_singleton"
DETAIL:  Key (singleton)=(t) already exists.
```

Reproduzido antes de corrigir (padrão desta auditoria): as fixtures
`http_database` (`tests/test_http_integration.py`) e `god_database`
(`tests/test_god_integration.py`) — nenhuma das duas tocada por nenhum
lote anterior, ambas datadas de antes desta sessão (13/07 e 17/07,
contra a migration `0024` criada às 21:24 de hoje) — inseriam **duas**
linhas reais em `creator` (`"creator"` e `"other"`) só para ter dois
IDs distintos disponíveis como `subject` de JWT em testes de identidade.
Isso nunca foi um problema até `uq_creator_singleton` (13.1) tornar
literalmente impossível existir uma segunda linha em `creator`, ponto
final — não é uma constraint por usuário, é uma constraint de tabela
inteira.

Investigado antes de decidir a correção: `get_sovereign_creator`
([backend/app/auth/dependencies.py:29-44](backend/app/auth/dependencies.py#L29-L44))
já busca **um único** Creator (`repository.get_one()`) e compara
`token_payload.sub` contra o `id` dele — a checagem de identidade nunca
dependeu de uma segunda linha real em `creator` existir; `other_id`
só precisava ser um UUID que não fosse o do Creator real. De 16 testes
quebrados, **15** falhavam só porque a fixture compartilhada inseria a
segunda linha sem nenhum teste individual precisar dela.

O 16º (`test_sovereign_creator_and_idor`,
[backend/tests/test_http_integration.py:132-142](backend/tests/test_http_integration.py#L132-L142))
era diferente: criava uma `Conversation` com `creator_id=other_id` (FK
real para `creator.id`) para provar que um recurso de "outro Creator"
devolve 404 (IDOR clássico). Com `other_id` proibido de existir como
linha real de `creator` (violaria `uq_creator_singleton` na hora de
inserir o Creator, e a FK da Conversation apontaria para uma linha
inexistente), esse cenário específico — "recurso pertence a um Creator
diferente" — deixou de ser representável no banco. Isso não é uma
lacuna de teste: é a Regra 1 sendo aplicada por construção agora, não
só em runtime — nunca mais poderá existir um segundo Creator cujo
recurso vazasse.

**Decisão registrada com o Criador antes de tocar no teste** (pergunta
explícita, resposta escolhida = opção recomendada): remover as duas
asserções que dependiam do cenário agora impossível (recurso de outro
Creator → 404), manter a asserção que continua válida e não depende de
uma segunda linha real (`subject` de token que não é o Creator
soberano → 403). Nenhuma cobertura de segurança real foi perdida — a
fronteira de identidade (`token_payload.sub != sovereign_id`) continua
100% testada; o que caiu foi só a checagem de ownership entre dois
Creators reais, cenário que a própria migration tornou impossível de
ocorrer em produção.

**Correção aplicada** (reproduzida → causa raiz confirmada →
corrigida, mesmo padrão desta auditoria):

| Arquivo | Mudança |
|---|---|
| `backend/tests/test_god_integration.py` | fixture `god_database`: removida a segunda linha `Creator(id=other_id, ...)`; `other_id` continua existindo só como `str(uuid.uuid4())`, usado apenas como `subject` de JWT em `auth(ids["other"])` |
| `backend/tests/test_http_integration.py` | fixture `http_database`: mesma remoção; import de `Conversation` removido (ficou não utilizado); `test_sovereign_creator_and_idor` reescrito — trocado o cenário "Conversation de um segundo Creator real → 404" (impossível agora) por "Conversation inexistente → 404" (continua válido), mantida a asserção "token de `other_id` → 403" |

Confirmado com `python -m ruff check backend` (`All checks passed!`)
e execução isolada dos dois arquivos corrigidos antes de repetir a
suíte inteira:

```
python -m pytest tests/test_god_integration.py tests/test_http_integration.py -q
.................                                                        [100%]
```

**17/17 nesses dois arquivos, 0 falhas.**

### 13.4 `pytest -v` completo, suíte inteira, banco de teste recriado do zero de novo

```
python -m pytest backend/tests -q
........................................................................ [ 21%]
........................................................................ [ 42%]
........................................................................ [ 64%]
........................................................................ [ 85%]
................................................                         [100%]
```

**340 testes, 340 pontos (`.`), zero `F`/`E`.** Apenas os mesmos 3
warnings de depreciação do FastAPI (`on_event`) já registrados antes,
não relacionados a este lote. (340 vs. 333 da seção 11: `+3` de
`test_auth.py`, mais os demais novos testes trazidos junto com a
migration `0024` fora do escopo desta sessão.)

### 13.5 Revisão de fluxos críticos (seção 9) — E2E real via PowerShell, contra a stack Docker

Login real (`POST /api/v1/auth/login`), depois transcript real via
`Invoke-RestMethod`:

```
1. POST /conversations + /messages                         → OK
2. POST /living-core/conversations/{id}/god                 → interaction_type "DIRECT_RESPONSE"
3. GET  /pulse → database ok, redis ok, chronicles_chain.valid=true,
   active_universes=3, active_agents=3
4. POST /inceptions → submit → approve                      → status "approved"
5. POST /missions → plan → validate → authorize              → status "authorized"
6. POST /agents/{knowledge_research_agent}/heartbeat          → refresca elegibilidade
7. POST /tasks (required_capability=knowledge_research real,
   input_json={topic, notes com 1 duplicata proposital})
   POST /tasks/{id}/ready
8. POST /dispatch                                             → mission "authorized" → "distributed"
9. polling GET /missions/{id} a cada 2s:
      [0..3] mission.status = executing
      [4]    mission.status = manifested
10. GET /tree-core/missions/{id}/consolidation → "complete"
    GET /central-core/missions/{id}/decision   → "APPROVED"
    GET /malkuth/missions/{id}/manifestation   → "MANIFESTED"
    GET /agents/executions?limit=5 → handler "knowledge_research", state "succeeded"
    GET /agents/executions/{id}/result →
      output.summary = "Knowledge synthesis for 'RC1 validacao': 2 organized point(s) from internal notes."
      output.key_points = ["nota 1", "nota 2"]   (3 notas enviadas, 1 duplicada de propósito → 2 deduplicadas)
      output.sources = ["internal-memory:mission:<id>", "internal-memory:task:<id>"]
11. GET /chronicles/verify → {"valid":true,"message":"Chronicle chain verified with no adulteration detected."}
```

Confirma ao vivo: DEUS Conversation, Pulse, Inception, Mission
Authorization, Dispatch/Execution (handler real `knowledge_research`,
saída deduplicada — não é `structured_echo` disfarçado), Consolidação,
Decisão, Manifestação, Chronicle/adulteração, Audit trail.

Não verificado nesta sessão (mesmas exceções já previstas pela
checklist e já registradas na seção 12.5, não re-testadas por não terem
mudado): **Voice** (requer microfone físico); verificação visual via
navegador do CSP/login (o fix de `frontend/nginx.conf` documentado na
seção 12.5 permanece idêntico — `git diff HEAD -- frontend/nginx.conf`
sem diferença — não repetido via Playwright nesta sessão); Opportunity
Discovery/Continuous Perception com chamada HTTP de saída real (fora de
escopo, mesmas 2 fontes seedadas com `enabled: false`).

### 13.6 Security gate (seção 10)

```
git status --short
git ls-files -- .env "*.sql" "backups/**" "*.log" "*.bak" "*.old" "*.tmp"
  → backups/BACKUPS.md        (único resultado, permitido pela checklist)
git check-ignore -v secrets/*.txt .env
  → todos os 5 arquivos de secrets usados + .env corretamente ignorados
```

Nenhum `.env`, segredo, backup além do permitido, log ou arquivo
temporário rastreado pelo git. `testwrite.tmp` (0 bytes, não rastreado,
resíduo de sessão anterior) segue no working tree — mesma observação já
registrada na seção 12.6, não bloqueia o gate, decisão de remoção fica
com o Criador.

### 13.7 P4/P5 — reverificação independente nesta sessão

Antes de repetir a conclusão da seção 12.7, os arquivos de teste atuais
foram varridos de novo (`grep` por `reclaim`, `lease_expire`, e por
qualquer teste que importe `app.worker` diretamente) para confirmar que
nada trazido junto com a migration `0024` ou qualquer outro trabalho
concorrente já fechou essas pendências.

- **P4 (reclaim de lease expirado, dois workers concorrentes) — CONTINUA
  ABERTO.** Mesmos dois testes já identificados na seção 12.7
  (`test_concurrent_lease_and_enqueue`,
  `test_concurrent_terminal_transitions_multiple_leases_and_cancel_race`
  em `test_dispatch_integration.py`, arquivo não modificado desde
  20/07) — corridas de primeira captura, não reclaim de lease já
  expirado por dois atores reais.
- **P5 (retry/backoff ponta a ponta pelo processo real do worker) —
  CONTINUA ABERTO.** Nenhum arquivo de teste em `backend/tests/`
  importa `app.worker` (`grep -r "from app.worker\|import app.worker"`
  sem resultado). O caminho "falha → retry → sucesso" através do loop
  real do processo `python -m app.worker` segue sem cobertura
  automatizada.

Nenhuma tentativa foi feita de escrever esses testes nesta sessão —
mesma decisão já registrada na seção 12.7, reafirmada: fechá-los é
trabalho de desenvolvimento de teste novo, fora do escopo de uma
checklist de hardening operacional.

### 13.8 Resumo do que foi corrigido nesta sessão

| Arquivo | Motivo |
|---|---|
| `backend/tests/test_god_integration.py` | fixture inseria uma 2ª linha real em `creator`, agora proibida por `uq_creator_singleton` (0024); a linha nunca era necessária, só o UUID como subject de JWT |
| `backend/tests/test_http_integration.py` | mesma causa raiz; adicionalmente, `test_sovereign_creator_and_idor` reescrito porque seu cenário (recurso de um 2º Creator real) ficou estruturalmente impossível sob o singleton — decisão tomada com o Criador antes de editar o teste |

Nenhuma arquitetura congelada, regra imutável ou escopo (Genesis, novos
Universos, destruição, shell arbitrário) foi tocado. Nenhuma tag, push,
restore de banco ou commit foi feito — aguardando autorização explícita
do Criador conforme seção 11 da checklist. A edição concorrente
detectada na seção 13.1 foi reportada ao Criador em tempo real durante
a sessão, não descoberta apenas neste registro final.

### 13.9 Confirmação final de estado, seção por seção da checklist

| Seção da checklist | Resultado |
|---|---|
| 1. Git State | OK — nenhum segredo/backup staged; branch é `fix/creator-interface-living-functional-scene`, não `main` (mesmo desvio já registrado na seção 12.1) |
| 2. Environment | OK — `.env` e `secrets/*` já existiam, íntegros |
| 3. Disposable Test Database | OK — recriado do zero 2×, nome contém `test` |
| 4. Backend Validation | OK após correção — ruff limpo, pytest 340/340 |
| 5. Frontend Validation | OK — 15/15 testes, build de produção OK, `dist/` não versionado |
| 6. Docker Validation | OK — config/build/up/ps, 5/5 serviços saudáveis, `package-lock.json` não modificado |
| 7. Health Checks | OK — live/ready, revisão `0024_creator_singleton` |
| 8. Database Readiness | OK — `alembic_version.version_num = 0024_creator_singleton` |
| 9. Critical Flow Smoke Review | OK para os fluxos testáveis sem hardware/rede externa (ver 13.5) |
| 10. Security Gate | OK |
| 11. Release Candidate Preparation | **Não executado** — sem tag, push, commit; aguardando autorização explícita |

---

## 11. Lote 2.6 — Fechamento e provas

### Prova 1 — seed aplicado em banco vazio: 12 Universos, exatamente 3 ativos

`docker compose down -v` + `docker compose up --build -d` (reset completo,
igual ao padrão dos lotes anteriores), depois query real:

```sql
SELECT code, name, active FROM universes ORDER BY active DESC, code;
```
```
     code      |     name     | active
---------------+--------------+--------
 engineering   | Engenharia   | t
 knowledge     | Conhecimento | t
 security      | Segurança    | t
 automation    | Automação    | f
 business      | Negócios     | f
 communication | Comunicação  | f
 design        | Design       | f
 evolution     | Evolução     | f
 finance       | Finanças     | f
 legal         | Jurídico     | f
 marketing     | Marketing    | f
 vision        | Visão        | f
(12 rows)
```
```sql
SELECT count(*) AS total, count(*) FILTER (WHERE active) AS active_count FROM universes;
```
```
 total | active_count
-------+--------------
    12 |            3
```

Agentes/capabilities seedados junto (mesma migration, mesma prova):

```
           code           |           name           |  universe   | universe_active | status  | enabled
--------------------------+--------------------------+-------------+-----------------+---------+---------
 engineering-design-agent | Engineering Design Agent | engineering | t               | offline | t
 knowledge-research-agent | Knowledge Research Agent | knowledge   | t               | offline | t
 security-review-agent    | Security Review Agent    | security    | t               | offline | t
```
```
        name
--------------------
 engineering_design
 knowledge_research
 planning
 security_review
```

`docker compose logs worker`: `authenticated as worker
00000000-0000-0000-0000-000000000001 (system-worker)` — as 4
capabilities (incluindo as 3 novas) já disponíveis para lease desde o
boot, sem passo manual.

### Prova 2 — teste automatizado: task para Universo inativo é rejeitada

`test_tree_core_postgres.py::test_agent_linked_to_inactive_universe_is_excluded_from_matching`
(Postgres real, não fake repo): registra um Agent ligado a
`Universe(code="security", active=False)` e um segundo Agent "legado"
sem `universe_id` (string livre, como todos os Agents pré-Lote-2.6).
Com o Universo inativo, `eligible_agents()` devolve só o legado
(`["Legacy Agent"]`) — o Agent governado some da lista, exatamente o
comportamento exigido ("Universo inativo nunca recebe task"). Ativando
o mesmo Universo (`active = True`) sem tocar em nada mais, o mesmo
Agent volta a aparecer (`["Legacy Agent", "Security Agent"]`) — prova
que o gate é dinâmico, não um artefato de cadastro.

### Prova 3 — os três agentes com teste unitário de saída tipada

`test_handler_registry.py`, 4 testes novos:
- `test_knowledge_research_handler_produces_deterministic_typed_output`
  — mesma entrada duas vezes → mesma saída; notas duplicadas/deduplicadas
  e ordenadas; `sources` deriva de `context.mission_id`/`task_id`.
- `test_engineering_design_handler_decomposes_requirements_deterministically`
  — requisitos duplicados/vazios tratados; `dependencies` deduplicadas e
  ordenadas.
- `test_security_review_handler_flags_sensitive_keys_and_is_compliant_otherwise`
  — payload com `api_key` é sinalizado (`risk_level=high`,
  `compliant=False`); payload limpo passa (`risk_level=low`,
  `compliant=True`). Reaproveita `SENSITIVE_KEYS` de
  `app/repositories/domain.py`, não reinventa a lista.
- `test_resolve_by_capability_finds_each_registered_handler_and_rejects_unknown`
  — os 4 handlers (incluindo `structured_echo`) resolvidos pela
  capability certa; capability desconhecida levanta `HandlerError`.

### Prova 4 — transcript E2E real via curl, usando um agente real (fecha P6)

Sequência real (mesmo método de corpo-via-arquivo do Lote 2.2, por causa
do bug de escaping do PowerShell 5.1 com JSON inline):

```
1.  POST /auth/login                                     → access_token
2.  POST /conversations + /messages
3.  POST /inceptions → submit → approve
4.  POST /missions → plan → validate → authorize          → status "authorized"
5.  GET  /capabilities                                     → knowledge_research id
    GET  /agents                                           → Knowledge Research Agent (seedado, status "offline")
    POST /agents/{id}/heartbeat                             → status "idle"
6.  POST /tasks  (required_capability=knowledge_research, input_json REAL:
                  topic="Consolidacao v0.5 - Lote 2.6",
                  notes=[3 notas, 1 duplicada de propósito])
    POST /tasks/{id}/ready
7.  POST /dispatch                                          → mission "authorized" → "distributed"
8.  polling GET /missions/{id}:
      [0] mission.status = executing
      [1] mission.status = manifested
9.  GET /agents/executions?limit=50 → execution real, handler="knowledge_research"/"1.0", state="succeeded"
    GET /agents/executions/{id}/result →
      output.summary = "Knowledge synthesis for 'Consolidacao v0.5 - Lote 2.6': 2 organized point(s) from internal notes."
      output.key_points = ["Handler determinista, sem I/O", "Universos ativos: Conhecimento, Engenharia, Seguranca"]
      output.sources = ["internal-memory:mission:<id>", "internal-memory:task:<id>"]
      metrics = {"note_count": 3, "key_point_count": 2}
10. GET /chronicles/verify → {"valid":true,"message":"Chronicle chain verified with no adulteration detected."}
```

A nota duplicada nas 3 fornecidas virou 2 `key_points` deduplicados e
ordenados — prova de que a saída veio do handler `knowledge_research`
de verdade (não de `structured_echo`, que ecoaria o payload cru sem
transformar nada). Do `POST /dispatch` até `mission.status ==
"manifested"`: 2 ciclos de polling, zero SQL manual. **P6 do punch-list
fechado**: o handler que rodou não foi `structured_echo`.

### `pytest -v` completo, suíte inteira

Suíte completa: **333 testes coletados, 333 passaram, 0 falharam**
(328 do fechamento do Lote 2.2 + 5 novos deste lote: 4 em
`test_handler_registry.py`, 1 em `test_tree_core_postgres.py`).

```
================ 333 passed, 4 warnings in 3354.90s (0:55:54) =================
```

**Nota sobre o wall-clock (investigada, não atribuída por hábito à causa
anterior, conforme instruído)**: 3354s (~56min) é ~3,4× o baseline de
~989s (~16min) do Lote 2.2, mas **não** tem o padrão do incidente
anterior (40307s / ~11h, consistente com hibernação da máquina — uma
lacuna, não uma execução lenta). Diferença real identificada entre esta
execução e a mais rápida: desta vez a suíte rodou com a stack Docker
completa (`api`+`worker`+`postgres`+`redis`) ativa o tempo todo — em
particular o `worker` processo fazendo polling contínuo
(`POLL_INTERVAL_SECONDS=2`, heartbeat a cada 30s) contra o mesmo
servidor Postgres (instância única, bancos `the_creation_os` e
`the_creation_os_test` são catálogos separados mas competem por
CPU/IO/conexões do mesmo container). Essa é uma hipótese plausível e
verificável, coerente com a magnitude (3-4× mais lento, não 40×), mas
**não foi isolada por reexecução comparativa** (não rodei a suíte de
novo com a stack parada só para medir a diferença, por custo de tempo)
— registrado como hipótese razoável, não como fato provado.

### Punch-list — situação após este lote

- **P6 (handler único) fechado** — prova 4 acima.
- **P4/P5 seguem abertos**, sem mudança neste lote (não fazia parte do
  escopo autorizado); ficaram mais fáceis de escrever agora que existem
  3 handlers reais além de `structured_echo` para variar o cenário de
  retry/reclaim, mas isso não foi explorado aqui.

### Pendências verdadeiras deste lote

- Os 9 Universos inativos são só registro (código/nome/`active=false`),
  por design — sem pasta, lógica ou handler, conforme item 5 da
  autorização.
- `Task.universe_id` continua sem uso (decisão registrada na seção 10):
  a elegibilidade por Universo é decidida via `Agent.universe_id`, não
  via `Task.universe_id`.
- O router-order bug (`GET /agents/executions`) e o
  `EXPECTED_ALEMBIC_REVISION` desatualizado eram bugs pré-existentes,
  não introduzidos neste lote — mas só vieram à tona porque este lote
  exigiu subir o container e chamar o endpoint de verdade.

---

## 12. Finalização v1.0.0-rc1 — validação real e fechamento

Executado em 2026-07-21, seguindo `docs/RELEASE_CHECKLIST.md` seção por
seção, do zero (Docker Desktop reiniciado no meio da sessão — ver nota
abaixo), sem reaproveitar nenhuma conclusão anterior sem re-executar.

### 12.1 Git state (seção 1)

Branch de trabalho: `fix/creator-interface-living-functional-scene` (não
`main` — a checklist assume `main`, mas esta sessão validou o RC ainda na
branch de feature, antes do merge; registrado aqui como desvio conhecido,
não como falha). `git status --short` e `git diff --check` não
mostraram nenhum `.env`, backup `.sql`, log, cache ou credencial local
staged — apenas avisos de conversão LF/CRLF (esperado em Windows, não é
erro de whitespace real). Nenhum arquivo estava staged no início da
sessão.

### 12.2 Ambiente e Docker Desktop — incidente real durante a sessão

Ao tentar `docker ps` no início da sessão, o engine do Docker Desktop
devolveu `500 Internal Server Error` para `dockerDesktopLinuxEngine`,
inclusive para `docker version` (client respondia, server não). Os 5
containers do projeto apareceram depois como `Exited (255)`. Diagnóstico
antes de qualquer ação destrutiva:

- Múltiplos processos `Docker Desktop`/`com.docker.backend` com horários
  de início inconsistentes (alguns de mais de uma hora antes, misturados
  com processos novos) — sinal de estado travado, não necessariamente de
  crash fatal.
- Windows Event Log (`Application`, `System`, últimas 6h): nenhum evento
  de erro/aviso relacionado a `docker`, Hyper-V ou WSL2 na janela do
  incidente — sem dump de crash, sem falha de VM registrada.
- Criador reiniciou o Docker Desktop manualmente. `docker version` voltou
  a responder normalmente (client + server) logo em seguida.
- A pedido do Criador, rodado `com.docker.diagnose.exe gather` (bundle
  local, não upload — salvo em
  `%LOCALAPPDATA%\Temp\<ID>\20260721211049.zip`, na máquina do Criador).
  O histórico interno de eventos do backend (`GET /idle` via IPC) mostrou
  uma sequência limpa `docker: starting` → `docker: running` (~97s) →
  `dockerAPI: running (API proxy serving requests)` (~+217s), sem
  flapping repetido. As rotações de `monitor.log` mantêm uma cadência
  regular de ~24min ao longo de toda a sessão (antes e depois do
  incidente), consistente com rotação por tempo, não com um crash-loop.
  **Conclusão: hang transitório do backend (processo vivo, API não
  respondendo), não corrupção nem falha de VM — resolvido por um
  restart limpo.** Sem ação corretiva adicional necessária no projeto;
  registrado aqui porque consumiu parte real da sessão e o Criador pediu
  o diagnóstico explicitamente.

### 12.3 Ruff — falha real encontrada e corrigida (não coberta pela seção 1 da auditoria anterior)

`python -m ruff check backend` (nunca antes rodado nesta auditoria,
que até aqui só tinha `pytest`) apontou **6 erros reais, 0 dos quais
existiam antes desta sessão** — introduzidos junto com o código do Lote
2.2/2.6 ainda não commitado:

1. `backend/app/worker.py:20` — `F401`, `SYSTEM_WORKER_NAME` importado e
   nunca usado (confirmado por busca no arquivo inteiro). Corrigido
   removendo o nome do import.
2. `backend/tests/test_worker_orchestration.py` — `F811` em duas
   funções de teste (`test_concurrent_orchestration_produces_exactly_one_record_each`,
   `test_manual_route_stays_idempotent_during_automatic_orchestration`):
   o parâmetro da fixture `consolidation_db` (importada de
   `test_consolidation_integration.py` para reaproveitar setup, padrão
   já usado no arquivo com `# noqa: F401` no import) é sinalizado pelo
   Ruff como "redefinição" do próprio import. Este é o padrão normal de
   fixture-via-import do pytest, não um bug real — corrigido com
   `# noqa: F811` nas duas assinaturas de função, sem alterar
   comportamento.
3. 3 blocos de import desordenados (`I001`) em
   `0023_universe_agent_seed.py`, `tests/conftest.py` e
   `test_worker_orchestration.py` — cosméticos, corrigidos com
   `ruff check backend --fix` (reordena imports, não toca lógica).

`python -m ruff check backend` após as correções: `All checks passed!`

### 12.4 Backend: banco de teste descartável + pytest + Docker (seções 3, 4, 6, 7, 8)

```
docker compose config    → resolve sem erro; worker aparece na resolução
                            padrão (não mais atrás de future-runtime,
                            conforme já registrado no Lote 2.2)
docker compose build     → 3 imagens (api, frontend, worker) built OK
docker compose up -d --force-recreate
docker compose ps
NAME                       STATUS
thecreationos-api-1        Up (healthy)
thecreationos-frontend-1   Up (healthy)
thecreationos-postgres-1   Up (healthy)
thecreationos-redis-1      Up (healthy)
thecreationos-worker-1     Up (healthy)
```

```
GET /api/v1/health/live  → {"status":"live"}
GET /api/v1/health/ready → {"status":"ready"}
psql ... SELECT version_num FROM alembic_version;
  → 0023_universe_agent_seed   (bate com o esperado)
```

Banco de teste descartável recriado do zero (não reaproveitado):

```
docker exec ... psql ... "SELECT pg_terminate_backend(...) WHERE datname='the_creation_os_test' ..."
docker exec ... dropdb -U postgres the_creation_os_test
docker exec ... createdb -U postgres the_creation_os_test
```

```
$env:TEST_DATABASE_URL='postgresql+asyncpg://postgres:***@localhost:5432/the_creation_os_test'
python -m pytest backend/tests -q
........................................................................ [ 21%]
........................................................................ [ 43%]
........................................................................ [ 64%]
........................................................................ [ 86%]
.............................................                            [100%]
```

**333 testes, 333 pontos (`.`), zero `F`/`E`** — 333/333 passaram, 0
falharam, batendo exatamente com o total registrado no fechamento do
Lote 2.6 (seção 11). Apenas warnings de depreciação do FastAPI
(`on_event` → lifespan handlers), pré-existentes, não relacionados a
este lote.

### 12.5 Revisão de fluxos críticos (seção 9) — E2E real, achado e corrigido em campo

Login como Creator via `POST /auth/login`, depois transcript real via
`Invoke-RestMethod` (não simulado):

```
1. POST /conversations + /messages                       → OK
2. POST /inceptions → submit → approve                    → status "approved"
3. POST /missions → plan → validate → authorize            → status "authorized"
4. POST /agents/{knowledge_research_agent}/heartbeat        → status "idle"
   (heartbeat do agente seedado estava obsoleto, de uma sessão anterior;
   sem refresh, /dispatch responde "No compatible agent" — comportamento
   correto do sistema, não um bug: heartbeat realmente vencido)
5. POST /tasks (required_capability=knowledge_research, input_json real)
   POST /tasks/{id}/ready
6. POST /dispatch                                          → mission "authorized" → "distributed"
7. [0] GET /missions/{id} → status = "manifested"           (já no primeiro poll)
8. GET /tree-core/missions/{id}/consolidation → "complete"
   GET /central-core/missions/{id}/decision   → "APPROVED"
   GET /malkuth/missions/{id}/manifestation   → "MANIFESTED"
   GET /agents/executions?limit=5 → handler "knowledge_research", state "succeeded",
       output real transformado (3 notas, 1 duplicada → 2 key_points deduplicados)
9. GET /chronicles/verify → {"valid":true,"message":"Chronicle chain verified with no adulteration detected."}
```

Confirma ao vivo, nesta sessão: DEUS Conversation, Inception, Mission
Authorization, Dispatch/Execution (handler real, não echo), Chronicle,
Audit trail, decisions. `GET /universes`, `/capabilities`, `/agents` e
`/pulse` conferidos e batendo com o seed (12 Universos, 3 ativos, 4
capabilities, 3 agentes seedados + `planning`).

**Achado real nesta sessão — bug de severidade alta, não registrado em
nenhum lote anterior**: usando Playwright (instalado nesta sessão só
para esta verificação visual, com autorização do Criador) para abrir a
Creator Interface de verdade no navegador (`http://127.0.0.1:5173`) e
tentar login, o console mostrou:

```
Connecting to 'http://127.0.0.1:8000/api/v1/auth/login' violates the
following Content Security Policy directive: "connect-src 'self' https:".
```

A tela mostrava "CRIADOR DESCONECTADO" / "Falha ao autenticar o
Criador" — **login via navegador estava 100% quebrado na configuração
padrão do `docker compose up`**, mesmo com a API saudável e todos os
testes de integração via `curl`/`Invoke-RestMethod` passando (esses
nunca passam pelo CSP do navegador, por isso o bug nunca apareceu em
nenhum teste automatizado ou transcript anterior). Causa raiz:
[frontend/nginx.conf](frontend/nginx.conf) define
`connect-src 'self' https:` — mas `VITE_API_BASE_URL` é
`http://127.0.0.1:8000/api/v1` (build arg do `docker-compose.yml`, HTTP
simples, sem TLS termination configurada em lugar nenhum do projeto).
Todo `fetch` do bundle para a API era bloqueado pelo próprio navegador
antes de sair.

**Correção**: `connect-src` passou a incluir explicitamente
`http://127.0.0.1:8000` (a origem exata já embutida no bundle via
`VITE_API_BASE_URL`, mesmo valor, nenhuma abertura nova), mantendo
`https:` para quando um deployment real usar TLS na frente. Frontend
reconstruído (`docker compose build frontend` +
`up -d --force-recreate frontend`) e reverificado com o mesmo script
Playwright: login sucede, dashboard renderiza (constelação
DEUS/SOPHIA/ROCKMAM, badge "Pulso Verificando"/"Pulso Ativo" com "3
agentes ativos / 0 inceptions pendentes"), **zero erros de console**.
Viewport mobile (390×844) também verificado: layout responsivo,
mesma badge de Pulso com dados ao vivo, input de chat adaptado.
Screenshots desta verificação não fazem parte do commit (ficaram no
scratchpad da sessão), mas o diff de `frontend/nginx.conf` está
disponível para revisão.

Não verificado nesta sessão (mesmas exceções já previstas pela
checklist): **Voice** — requer microfone físico, indisponível neste
ambiente; registrado como nota de release, não como bloqueio. Opportunity
Discovery e Continuous Perception: endpoints confirmados alcançáveis e
em estado seguro por padrão (`enabled: false` nas 2 fontes de percepção
seedadas), lógica profunda já coberta pelos 333 testes automatizados —
não executei uma descoberta real (faria chamadas HTTP de saída reais
para Yahoo Finance/GitHub, fora do escopo desta validação).

### 12.6 Security gate (seção 10)

```
git status --short           → nada staged; mesma lista de M/D/?? já
                                conhecida do início da sessão, mais
                                frontend/nginx.conf (correção desta sessão)
git ls-files -- .env "*.sql" "backups/**" "*.log" "*.bak" "*.old" "*.tmp"
  → backups/BACKUPS.md        (único resultado, permitido pela checklist)
```

Nenhum `.env`, segredo, backup além do permitido, log ou arquivo
temporário está rastreado pelo git. `secrets/*` confirmado ignorado
arquivo por arquivo (`git check-ignore -v`). Um arquivo solto
`testwrite.tmp` (0 bytes, não rastreado, provavelmente resíduo de sessão
anterior) segue no working tree — não bloqueia o gate (não está staged
nem rastreado), mas fica registrado aqui para o Criador decidir se quer
removê-lo.

### 12.7 P4/P5 — verificação independente, não apenas repetição do que a auditoria já dizia

Antes de simplesmente confirmar o que a seção 11 já registrava, os
arquivos de teste foram lidos de novo nesta sessão para verificar se
algo mudado no código ainda não commitado já os teria fechado. Não
fechou.

- **P4 (reclaim de lease expirado, dois workers concorrentes) — CONTINUA
  ABERTO.** `test_concurrent_lease_and_enqueue` e
  `test_concurrent_terminal_transitions_multiple_leases_and_cancel_race`
  ([backend/tests/test_dispatch_integration.py](backend/tests/test_dispatch_integration.py))
  usam `asyncio.gather` real contra Postgres real, mas para dois workers
  disputando um item **nunca antes arrematado** (corrida de primeira
  captura), não um lease **já expirado** que um primeiro worker perdeu.
  `test_dispatch_error_paths_expiration_acknowledge_and_release` testa
  expiração, mas com um único ator sequencial que força
  `lease_expires_at` manualmente para o passado e depois arremata de
  novo — não dois workers reais competindo simultaneamente pelo mesmo
  lease expirado.
- **P5 (retry/backoff ponta a ponta pelo processo real do worker) —
  CONTINUA ABERTO.** `test_worker_orchestration.py` inclui o comentário
  explícito "Mirrors app.worker._try_close_out_mission exactly" — o
  teste reimplementa a lógica da cauda do worker via um helper de teste
  chamando os services diretamente; nenhum teste importa ou executa
  `app/worker.py` de verdade. O backoff exponencial em si já é testado
  no nível de serviço (`test_dispatch_service.py`, reaproveitado, não
  novo), mas o caminho "falha → retry → sucesso" através do loop real do
  processo `python -m app.worker` não tem cobertura automatizada.

Nenhuma tentativa foi feita de escrever esses testes nesta sessão —
fechá-los é trabalho de desenvolvimento de teste novo, fora do escopo de
uma checklist de hardening operacional, e não foi pedido explicitamente
além da confirmação de status.

### 12.8 Resumo do que foi corrigido nesta sessão

| Arquivo | Motivo |
|---|---|
| `backend/app/worker.py` | Import não utilizado (`SYSTEM_WORKER_NAME`), achado real do Ruff |
| `backend/tests/test_worker_orchestration.py` | `# noqa: F811` em 2 assinaturas (falso positivo do padrão fixture-via-import do pytest) |
| `backend/alembic/versions/0023_universe_agent_seed.py`, `backend/tests/conftest.py`, `backend/tests/test_worker_orchestration.py` | Reordenação de imports (`ruff --fix`, cosmético) |
| `frontend/nginx.conf` | CSP bloqueava 100% do login via navegador contra a API HTTP local do `docker-compose.yml` — bug de severidade alta, nunca coberto por teste `curl`/`pytest` |

Nenhuma arquitetura congelada, regra imutável ou escopo (Genesis, novos
Universos, destruição, shell arbitrário) foi tocado. Nenhuma tag, push,
restore de banco ou commit foi feito — aguardando autorização explícita
do Criador conforme seção 11 da checklist.
