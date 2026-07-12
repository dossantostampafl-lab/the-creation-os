# THE CREATION OS v0.3 — Living Core

Projeto backend do núcleo persistente do THE CREATION OS. Inclui autenticação do Criador, conversa com GOD, Trindade, Inceptions, Central Core, Tree Core, Universos, memória, Chronicles e Pulse.

## Arquitetura

- `api` expõe REST estável `/api/v1`
- `auth` gerencia o único Criador e tokens JWT
- `chronicles` mantém histórico append-only encadeado
- `core` executa a lógica de GOD, SOPHIA, ROCKMAM, Central Core, Tree Core e Malkuth
- `memory` implementa memória de conversa, missão, universo e consciousness
- `db` e `alembic` gerenciam persistência PostgreSQL
- `redis` e `redis streams` suportam execução de tarefas

## Requisitos

- Docker
- Docker Compose
- Python 3.12 (para execução local sem container)

## Configuração

Copie `.env.example` para `.env` e ajuste os valores.

## Executar local

```bash
docker compose up --build
```

## Migrations

```bash
docker compose exec api alembic upgrade head
```

## Criar o Criador

```bash
curl -X POST http://localhost:8000/api/v1/auth/bootstrap \
  -H "Content-Type: application/json" \
  -d '{"username":"creator","password":"change-me-securely"}'
```

## Login

```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"creator","password":"change-me-securely"}'
```

## Endpoints principais

- `POST /api/v1/auth/login`
- `POST /api/v1/conversations`
- `POST /api/v1/conversations/{id}/messages`
- `GET /api/v1/inceptions`
- `POST /api/v1/inceptions/{id}/approve`
- `POST /api/v1/inceptions/{id}/reject`
- `GET /api/v1/pulse`
- `GET /api/v1/chronicles`
- `GET /api/v1/chronicles/verify`

## Testes

```bash
cd backend
pytest
```
