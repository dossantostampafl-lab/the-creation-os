# PROMPT — Finalização do Release Candidate v1.0.0-rc1

## Atualização: mudança de frontend não verificada visualmente

Depois que o checklist completo já tinha passado 100% (340/340 pytest,
frontend 15/15 + build, Docker 5/5 saudável, `docs/AUDIT_v0.5.md` §13), o
Criador apontou que a Creator Interface renderizada em produção não é a
interface pretendida — o refator desta sessão havia trocado a cena cósmica
original (DEUS/SOPHIA/ROCKMAM + Universos como constelações + Pulse +
Crônicas, preservada no commit `8d24505` "restore frozen living universe
experience") por um dashboard mais simples. A decisão do Criador foi: manter
a base funcional (canvas `LivingUniverseScene` já ligado a dados reais de
`agents`/`universes`/`pulse`), e adicionar de volta a apresentação visual
rica como camada DOM sobre ela — não reverter o trabalho funcional.

Três arquivos novos foram criados e integrados em
`frontend/src/components/LivingDashboard.tsx`:

- `SystemPulseHeader.tsx` — barra superior com logo, onda de pulso
  animada e placar de saúde (`computePulseScore`, derivado só de
  `pulse.database/redis/redis_streams/chronicles_chain/failed_tasks/error_count`
  reais, sem número fabricado) e badge do Criador.
- `UniverseConstellationLabels.tsx` — cards persistentes para SOPHIA/
  ROCKMAM e para cada Universo ativo (nome, ícone, descrição, contagem real
  de agentes via `agents.filter(a => a.enabled && a.universe === code)`),
  com os 9 Universos inativos resumidos numa faixa compacta separada (não
  inventei Universos "ativos" que não existem no seed real).
- `ChronicleTicker.tsx` — rodapé persistente com os eventos recentes reais
  de `chronicles` (já buscados em `App.tsx`), com um mapeamento de
  `event_type` para frase curta em português, e botão que abre o painel
  completo já existente (`ChronicleRibbon`, inalterado).

A imagem de referência do Criador rotula o núcleo central como "GOD", mas
ele pediu explicitamente para manter o rótulo do app como "DEUS" — isso foi
cogitado e revertido nesta mesma sessão; não troque esse texto.

CSS novo foi anexado a `frontend/src/styles/living-dashboard.css`
(cabeçalho, cards de constelação, rodapé de crônicas) e os elementos
existentes (`conversation-dock`, `creator-access`, `transient-response`,
`system-state-binding`) foram reposicionados para não sobrepor o novo
rodapé.

**Isso é a parte que mais precisa da sua atenção agora**: não consegui
rodar `tsc --noEmit` nem `npm run build`/`npm run test` neste ambiente (o
sandbox ficou consistentemente lento/indisponível na sessão). Só verifiquei
manualmente balanceamento de chaves/parênteses e coerência de tipos por
leitura — não é o mesmo que compilar. Antes de qualquer outra coisa:

```powershell
Set-Location frontend
npm run test
npm run build
Set-Location ..
```

Se `tsc`/`vite build` apontar erro de tipo, o mais provável é em
`LivingDashboardProps` (novo campo `chronicles` e `onSelectPanel`) ou no
`App.tsx` (chamada de `<LivingDashboard>` — precisa passar `chronicles={chronicles}`
e `onSelectPanel={setRequestedPanel}`, ambos já adicionados). Depois do
build passar, suba o stack (`docker compose up -d --force-recreate`) e
**olhe a interface de verdade** em `http://127.0.0.1:5173` — layout,
sobreposição entre o rodapé de crônicas e a caixa de conversa, e os cards de
Universo/SOPHIA/ROCKMAM precisam de aprovação visual do Criador, não só
compilar sem erro.


Cole este prompt no Claude Code (ou outro agente com acesso real a Docker,
rede e shell na sua máquina), rodando na raiz do repositório
`THE CREATION OS`.

---

Você está retomando o THE CREATION OS, hoje na branch
`fix/creator-interface-living-functional-scene`, com um refator grande já
implementado mas ainda não commitado (~250 arquivos). Esse trabalho já foi
auditado em detalhe em `docs/AUDIT_v0.5.md`, incluindo uma execução completa
da suíte (333/333 testes) contra PostgreSQL + Redis reais via Docker. Seu
objetivo agora é **fechar o release candidate `v1.0.0-rc1`**, não adicionar
funcionalidade nova.

## Regras não negociáveis

- Não altere a arquitetura congelada nem as regras imutáveis descritas em
  `ARCHITECTURE.md` e no restante da documentação em `docs/`.
- Não implemente nada fora de escopo (sem Genesis, sem novos Universos, sem
  destruição total, sem execução arbitrária de shell vinda de IA).
- Não declare teste aprovado sem executá-lo de verdade. Não esconda falha.
  Não remova teste para forçar resultado verde. Não use banco em memória no
  lugar dos testes de integração reais.
- Leia `docs/AUDIT_v0.5.md` e `docs/RELEASE_CHECKLIST.md` inteiros antes de
  tocar em qualquer arquivo — eles documentam decisões já tomadas e o motivo
  de cada uma; não as reabra sem necessidade real comprovada por evidência.

## O que já foi verificado (sessão anterior, sem Docker/rede disponíveis)

- Toda a árvore Python (`backend/app`, `backend/tests`, `backend/alembic`)
  compila sem erro de sintaxe.
- `tsc --noEmit` no frontend passa sem erro de tipo.
- Nenhum segredo, `.env` ou backup `.sql` está versionado; `.gitignore` está
  correto.
- `docker-compose.yml` revisado manualmente: serviços, healthchecks,
  Docker secrets e volumes coerentes com o README.
- Corrigida inconsistência de documentação: `README.md`, `ARCHITECTURE.md`,
  `backend/README.md`, `backend/MIGRATIONS.md` e
  `docs/RELEASE_CHECKLIST.md` citavam o head Alembic antigo
  (`0022_pgvector_extension`); atualizados para acompanhar o head real.
- **Achado de segurança/concorrência, com correção escrita mas NÃO testada
  contra Postgres real**: `AuthService.bootstrap()`
  (`backend/app/services/auth.py`) fazia check-then-insert sem lock nem
  guarda no banco — nada impedia duas requisições concorrentes de
  `POST /api/v1/auth/bootstrap`, com usernames diferentes, de criarem dois
  Criadores (só existia `UNIQUE(username)`). Isso viola a Regra 1 da
  constituição. Nenhum teste cobria esse cenário. Escrevi:
  - `backend/alembic/versions/0024_creator_singleton.py` — coluna
    `singleton` boolean com `CHECK (singleton IS TRUE)` +
    `UNIQUE (singleton)`, padrão clássico de "tabela singleton" no
    Postgres;
  - `AuthService.bootstrap()` agora captura `IntegrityError` e traduz para
    409;
  - `backend/tests/test_auth.py` (novo arquivo): round-trip da migration
    0024, teste sequencial (segundo bootstrap rejeitado) e teste de
    concorrência real via `asyncio.gather` com dois usernames diferentes,
    exigindo exatamente um 201 e um 409, e exatamente uma linha em
    `creator` ao final.
  - `EXPECTED_ALEMBIC_REVISION` em `backend/app/api/health.py` e todas as
    referências de head nos docs foram atualizadas para
    `0024_creator_singleton`.
  - **Isso é a parte que mais precisa da sua atenção**: escrevi esse código
    sem conseguir rodar `alembic upgrade head` nem pytest contra Postgres
    real neste ambiente. Rode `backend/tests/test_auth.py` primeiro,
    isoladamente, antes do resto do checklist:
    `python -m pytest backend/tests/test_auth.py -v`.

Nada disso substitui execução real. Rode tudo de novo do zero.

## Ordem de execução

1. `git status --short` e `git diff --check` — confirme que nada
   inesperado está staged (sem `.env`, backups, logs, credenciais).
2. Gere `secrets/` com `.\scripts\generate-secrets.ps1` se ainda não
   existir.
3. Rode a sequência completa de `docs/RELEASE_CHECKLIST.md`, seção por
   seção, na ordem em que está escrita — não pule etapas:
   - validação de ambiente;
   - banco de teste descartável (`TEST_DATABASE_URL` contendo `test`);
   - `python -m pytest backend/tests -q`;
   - `python -m ruff check backend`;
   - `npm run test` e `npm run build` em `frontend/`;
   - `docker compose config`, `docker compose build`,
     `docker compose up -d --force-recreate`, `docker compose ps`;
   - `GET /api/v1/health/live` e `GET /api/v1/health/ready`;
   - conferir `alembic_version.version_num` contra a head real reportada
     por `alembic heads` (rodado em `backend/`) — não uma revisão fixa;
   - revisão dos fluxos críticos listados na seção 9 do checklist;
   - security gate (seção 10).
4. Corrija qualquer falha real encontrada, seguindo o mesmo padrão de
   investigação de `docs/AUDIT_v0.5.md` (reproduzir antes de supor causa,
   registrar o achado e a correção).
5. Se tudo passar, registre o resultado real em `docs/AUDIT_v0.5.md` (nova
   seção, com a prova/output de cada comando) — não em texto solto na
   entrega.
6. Não crie tag, não dê push, não restaure banco, não faça limpeza
   destrutiva e não commite sem minha autorização explícita, mesmo que tudo
   passe (seção 11 do checklist).

## Entrega obrigatória ao final

- Resultado real (output colado) de cada comando da seção 3 acima.
- Lista do que foi corrigido, com arquivo e motivo.
- Confirmação explícita se as pendências P4/P5 registradas em
  `docs/AUDIT_v0.5.md` (reclaim de lease com dois workers concorrentes;
  retry/backoff ponta a ponta com o processo real do worker) foram
  fechadas com prova de execução real, ou se seguem abertas.
- Pendências e limitações reais que restarem.
