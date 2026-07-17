# THE CREATION OS - MVP

Backend FastAPI, PostgreSQL, Redis e Creator Interface React/Vite.

## Pre-requisitos

- Docker e Docker Compose
- Node.js 20 para execucao local do frontend sem Docker
- Python 3.12 para execucao local do backend sem Docker

## Ambiente

1. Copie `.env.example` para `.env`.
2. Ajuste `APP_SECRET_KEY` e `CREATOR_BOOTSTRAP_PASSWORD`.
3. Nao preencha `GITHUB_TOKEN` salvo quando for validar o connector GitHub.

Variaveis principais:

- `DATABASE_URL`: conexao async do PostgreSQL usada pela API.
- `REDIS_URL`: conexao Redis usada por Pulse e filas.
- `CREATOR_BOOTSTRAP_USERNAME`: usuario inicial do Criador.
- `CREATOR_BOOTSTRAP_PASSWORD`: senha inicial do Criador.
- `VITE_API_BASE_URL`: base REST usada pelo frontend.

## Iniciar com Docker

```bash
docker compose config
docker compose build
docker compose up -d
docker compose ps
```

A API aplica migrations automaticamente ao iniciar.

## Criar ou acessar o Criador

Em banco limpo, crie o Criador uma unica vez:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/auth/bootstrap \
  -H "Content-Type: application/json" \
  -d "{\"username\":\"creator\",\"password\":\"change-me-securely\"}"
```

Depois acesse a interface com:

- usuario: `creator`
- senha: valor de `CREATOR_BOOTSTRAP_PASSWORD`

## Enderecos

- Frontend: http://127.0.0.1:5173
- Backend: http://127.0.0.1:8000/api/v1
- Healthcheck: http://127.0.0.1:8000/api/v1/health/ready

## Fluxo principal do MVP

1. Abra o frontend.
2. Faça login como Criador.
3. Confirme Pulse, Chronicle e dados reais carregados.
4. Abra o painel `CAPABILITIES`.
5. Liste capabilities registradas.
6. Habilite ou desabilite uma capability permitida.
7. Execute `REST seguro`.
8. Confirme resposta da automation na interface.
9. Para validar negacao, desabilite `Restricted REST Request` e execute novamente; o governance deve negar antes do connector.

## Fluxo de oportunidades v1.1

1. Faça login como Criador.
2. Use a área `OPORTUNIDADES`.
3. Execute `Descobrir` para enviar fixtures controladas ao backend.
4. O backend valida a capability `opportunity.discovery.run` pelo `CapabilityGovernanceService`.
5. Observações são normalizadas, deduplicadas e correlacionadas.
6. Oportunidades são pontuadas com:

```text
priority_score =
  confidence * 0.35
  + impact * 0.30
  + urgency * 0.20
  + source_reliability * 0.15
  - risk_penalty
```

7. O Criador pode aprovar ou rejeitar uma oportunidade.
8. Somente oportunidade aprovada pode ser convertida em Inception.
9. Nenhuma Mission ou operação financeira é criada automaticamente.

Endpoints principais:

- `GET /api/v1/observations`
- `POST /api/v1/observations`
- `GET /api/v1/opportunities`
- `GET /api/v1/opportunities/{id}`
- `GET /api/v1/opportunities/ranking`
- `POST /api/v1/opportunities/discovery/run`
- `POST /api/v1/opportunities/{id}/approve`
- `POST /api/v1/opportunities/{id}/reject`
- `POST /api/v1/opportunities/{id}/convert-to-inception`

Capabilities registradas:

- `opportunity.observation.collect`
- `opportunity.observation.ingest`
- `opportunity.discovery.run`
- `opportunity.discovery.expire`
- `opportunity.ranking.list`
- `opportunity.review`
- `opportunity.convert_to_inception`

## Testes

Backend focado:

```bash
cd backend
python -m pytest tests/test_capability_governance.py tests/test_capability_persistence.py tests/test_capabilities.py tests/test_automation.py -q
python -m pytest tests/test_opportunities.py -q
python -m pytest -m integration tests/test_opportunities_http.py -q
```

Frontend:

```bash
cd frontend
npm run build
```

Checks finais:

```bash
git diff --check
```

## Logs

```bash
docker compose logs api
docker compose logs frontend
docker compose logs postgres
docker compose logs redis
```

## Parar

```bash
docker compose down
```

Use `docker compose down -v` apenas quando desejar apagar volumes locais.

## Limitacoes conhecidas do MVP

- O connector GitHub exige `GITHUB_TOKEN` e allowlist configurados.
- O connector REST restrito permite somente hosts e metodos definidos no registry.
- Sem embeddings ou LLM externos obrigatorios neste MVP.
- O frontend executa somente o fluxo principal de capabilities/automation; recursos avancados permanecem no backend.
- O fluxo v1.1 usa execução manual e fixture controlada; não há scheduler recorrente nesta versão.
- O universo financeiro é exclusivamente informativo e investigativo; não executa compra, venda, transferência ou movimentação de ativos.
