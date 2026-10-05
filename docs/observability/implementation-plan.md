# Plano de execução

1. P0: adicionar SDK/exporters compatíveis e inicialização opt-in; testes de redaction e exportação não bloqueante.
2. Instrumentar FastAPI/HTTPX e spans de domínio de DEUS, LLM, STT/TTS, wake word, tarefas e ciclos, com atributos fechados.
3. Collector/Tempo privados, datasource Grafana, script de ativação com backup e checagem real. Validar uma trace após uma operação controlada.
4. P1: métricas OTLP, snapshot agregado, Prometheus, ingestão Loki restrita a eventos seguros e correlação trace-to-log.
5. Provisionar e validar dashboards DEUS, Voice, LLM, Agentes, Missões, Opportunity Fabric, Cyber Range e infraestrutura.
6. Revisão independente, CI e implantação; executar Gauntlet e consultas reais às três fontes. Registrar limites e acesso por túnel autenticado.

Implementação sequencial no workspace isolado existente. Não alterar código antigo de voz nem adicionar provedores pagos. A telemetria não recebe autoridade de execução.
