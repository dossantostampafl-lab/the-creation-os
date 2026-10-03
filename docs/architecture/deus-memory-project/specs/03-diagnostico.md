# S3 — observador independente do OS

## Escopo

Processo python -m app.diagnostics.worker, separado de missões, sem depender de LLM_PROVIDER. Detecção e incidentes determinísticos; DEUS recupera esses registros e oferece explicação. Primeira versão não reinicia containers, edita arquivos de produto, executa shell arbitrário ou faz ordens de trading.

Usar configuração de instância que resolva creator soberano autorizado; se não resolver, modo local-only com alerta de configuração, sem atribuir histórico arbitrariamente a outro Creator. Dados de host pertencem à administração daquela instância; não replicar para todas as contas.

## Contratos

Observation(id UUID,resource,rule,status healthy|unhealthy|unknown,observed_at,valid_until,latency_ms nullable,safe_evidence). Incident(id,creator_id,fingerprint,resource,rule,state open|acknowledged|recovered,first_seen,last_seen,recovered_at nullable,observation_ids). CauseHypothesis separada de observation, autoria e status hypothesis.

RuleEvaluator.evaluate(observations,previous_state) -> IncidentTransitions; DiagnosticsCollector.collect(now) -> list[Observation]; DiagnosticsJournal.append(observation) e replay(ack_cursor). Ingestão usa KnowledgeService com source_type diagnostic_observation/diagnostic_incident registrados explicitamente.

## Sondagens e defaults

API health, DB SELECT1/migration, RedisPING, indexer heartbeat/checkpoint, worker heartbeat e métricas de tarefas sem avanço. Métricas de inferência/voz derivam de execuções reais; não chamar fornecedor/TTS periodicamente para fabricar saúde ou consumir quotas. MCP health só para servidores realmente configurados e autorizados, sem instalar todos.

Intervalo15s, timeout porprobe2s, janela de validade45s, abrir após3 falhas consecutivas, recuperar após2 sucessos consecutivos. Pendência de fila e tarefas exige regra por duração configurada; running sozinho não prova travamento. Registrar estados de inferência como última execução observada, unknown se expirou.

Não montar docker.sock nem credenciais globais no coletor. Primeira versão conhece serviços por endpoints/protocolo e heartbeats internos. Disco via filesystem statvfs de caminho permitido. Diagnóstico detalhado Docker/container é extensão opcional com adapter estreito e revisado.

## Durabilidade e indisponibilidade

SQLite local privado em volume dedicado, máximo100MiB, journal com fsync, UUID idempotente e sequência própria. Persistir antes de enviar; confirmar entrega após commit do banco; replay preserva observed_at e creator-binding. Backpressure aplica retenção de7 dias a observações já confirmadas; pendentes não são removidas silenciosamente. Ao atingir limite, entrar spool_full, manter pequeno marcador reservado de falha e parar admitir novas amostras detalhadas; reportar contadores/drops explicitamente em health local. Não prometer preservação ilimitada nem observador sobreviver à queda do host.

Após DB voltar, subir observações em lotes100 com idempotência; horários antigos permanecem antigos. Não publicar observação healthy antiga como saúde atual. Redis indisponível não bloqueia journal/consulta durável. Heartbeat do próprio diagnóstico pode ser observado externamente; monitor externo está fora do MVP.

## Integração ao conhecimento

Incidentes abertos e observações válidas entram em fatos atuais via adapter do ContextBuilder. Histórico de incidente é conhecimento persistente. Mudança open→recovered cria nova revisão; episódio novo gera novo incidente, fingerprint com episódio e chave do recurso. Alertas repetidos só atualizam last_seen/evidência, sem inundar Chronicle poramostra.

Para worker heartbeat, registrar lease_owner, boot_id e observed_at em tabela própria. S3 detecta stale, não muda reconciler nem marca tarefa como fracassada. Recuperação de execução concorrente requer owner/fencing e fica num plano operacional posterior.
