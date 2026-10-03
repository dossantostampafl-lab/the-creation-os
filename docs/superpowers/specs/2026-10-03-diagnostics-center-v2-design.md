# Centro de Diagnóstico v2 — design

## Objetivo

Completar o Centro de Diagnóstico como subsistema interno e independente do THE CREATION OS, sem depender do Cyber Range e sem introduzir autocorreção, shell arbitrário, Docker socket ou chamadas periódicas a provedores de IA/TTS.

## Princípios

- Observador somente-leitura: detectar, registrar, correlacionar e publicar evidências; não reiniciar serviços nem alterar estado operacional.
- Fail-honest: ausência de evidência vira `unknown`, nunca `healthy`.
- Baseline preservada: PostgreSQL, Redis, API, fila de memória, disco e heartbeats continuam com os mesmos limites já validados.
- Incidentes continuam com histerese de 3 falhas para abrir e 2 sucessos para recuperar.
- Dados do diagnóstico permanecem vinculados ao Creator soberano e entram no contexto do DEUS apenas enquanto válidos.
- Cyber Range continua totalmente separado.

## Cobertura adicional

O observador passa a cobrir:
1. projeções do Chronicle: checkpoints ausentes, inválidos ou com lag acima do limite configurado;
2. tarefas em execução sem progresso por tempo superior ao limite configurado;
3. presença dos 12 Universos canônicos ativos;
4. saúde do próprio journal local, inclusive `spool-full`;
5. inferência como `unknown` enquanto não houver telemetria persistida segura; voz local validada somente pela presença dos artefatos Kokoro/Vosk quando a sessão de voz estiver habilitada.

## Estado ternário

Uma sonda retorna `healthy`, `unhealthy` ou `unknown`. `unknown` atualiza a validade da observação, mas não abre nem recupera incidente e não é contabilizado como sucesso/falha.

## Incidentes duráveis

A abertura de incidente recebe um `episode_id` imutável. A recuperação revisa o mesmo item do episódio. Observações correntes continuam expirando em 45 segundos; incidentes não expiram e permanecem como histórico auditável. Um novo episódio do mesmo recurso recebe outro `episode_id`.

## Proveniência


Revisões de conhecimento geradas pelo Centro usam fonte tipada:
- `diagnostic_observation`
- `diagnostic_incident`

O `source_id` é o UUID imutável do registro local. A elegibilidade recalcula um hash determinístico desse identificador. Isso melhora rastreabilidade sem introduzir dependência externa ou autoridade adicional.

## Configuração

Novos defaults:
- `DEUS_DIAGNOSTICS_TASK_STALL_SECONDS=900`
- `DEUS_DIAGNOSTICS_PROJECTION_MAX_LAG=100`

## Segurança e limites

- nenhuma chamada de provedor ou síntese TTS é feita para fabricar saúde; a voz é local e o observador apenas inspeciona os artefatos necessários;
- nenhum acesso a Docker socket;
- nenhuma escrita em entidades de missão/tarefa/projeção;
- nenhum vínculo com Cyber Range;
- nenhuma elevação de privilégio;
- nenhuma mutação automática de produção.

## Aceitação

A entrega é aceita quando:
- testes novos falham no baseline e passam com a implementação;
- suíte de backend, Ruff e mypy passam;
- CI e smoke não regredirem;
- o endpoint atual de diagnósticos continuar compatível e refletir as novas superfícies;
- nenhuma alteração for necessária no Cyber Range.
