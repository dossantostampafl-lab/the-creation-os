# Observabilidade do Creation OS — P0 e P1

A solicitação define a sequência: primeiro OpenTelemetry, Collector, Grafana e Tempo com FastAPI, HTTP, LLM, STT/TTS, wake word e workers instrumentados; depois Prometheus, Loki e dashboards DEUS, Voice, LLM, Agentes, Missões, Opportunity Fabric, Cyber Range e infraestrutura.

## P0 — traces

Reutilizar o perfil observability e o Grafana existente. Acrescentar Collector OTLP HTTP privado e Tempo com armazenamento local persistente. SDK Python exporta em lote, com fila e timeout limitados, sem tornar o Collector uma dependência de disponibilidade do aplicativo. A instrumentação padrão cobre FastAPI e HTTPX; spans de domínio cobrem resposta DEUS, tentativas de LLM/fallback, STT, síntese TTS, detecção da wake word, execução de tarefas e ciclos de workers. Operações longas em background têm spans por ciclo/operação, não um único span infinito.

A ativação é explícita e o padrão desativado. Endpoint, sampling e serviço vêm da configuração. A mesma inicialização atende API e processos supervisionados, incluindo STF. Propagação W3C usa traceparent, sem baggage. A telemetria é observacional: não modifica autorização, idempotência, contratos, histórico ou resultados de missões.

O exporter remove atributos não permitidos, URLs completas/query, cabeçalhos, corpos, prompts, transcrições, áudio, respostas, SQL e detalhes/stack de exceções antes do OTLP. Exportar somente operações/rotas templadas, método/status HTTP, serviço, provedor, tipo de erro e medidas numéricas. O Collector tem uma segunda camada de filtragem. Logs próprios de telemetria são JSON com esquema fechado e correlação trace_id/span_id; não coletar indiscriminadamente os logs de conversas existentes.

Collector e Tempo não publicam portas no host. Grafana continua autenticado em loopback; usar porta 3300 como padrão para evitar conflito com a porta 3001 usada por instalações de FreeLLM. Preservar senha/porta configuradas. Tempo possui retenção limitada e volume privado. Se a coleta falhar, spans podem ser descartados, mas o aplicativo continua funcionando.

## P1 — métricas, logs e dashboards

Collector recebe métricas OTLP e oferece scrape privado para Prometheus. Loki existente recebe eventos estruturados permitidos, com labels de baixa cardinalidade; IDs de traces ficam em campos, com navegação para Tempo. Métricas incluem volume, duração, erros, fallback, primeira resposta/áudio, detecção de wake word e resultados de ciclos. Snapshot agregado do banco cobre estado dos agentes, tarefas/missões, oportunidades e campanhas. Coleta de infraestrutura não monta Docker socket nem expõe painéis publicamente.

Provisionar os oito dashboards como JSON versionado. Cada painel consulta métricas realmente emitidas; não preencher lacunas com números simulados. Rotas, serviços, estados e operações formam labels limitadas; IDs, nomes de usuários, textos e URLs não formam labels. Incluir disponibilidade da coleta para distinguir ausência de dados de um estado saudável.

## Verificação e implantação

Antes da instrumentação: testes de filtragem de dados, exportador indisponível e hierarquia de spans. Depois: testes existentes de chat/voz/workers e contratos Compose/YAML, SDK/exportação contra Collector real, trace consultável no Tempo e Grafana provisionado. P1 exige série consultável no Prometheus e evento seguro no Loki, além dos oito dashboards provisionados. A validação final repete o Gauntlet no site com telemetria ativa, preservando a descoberta pública. Microfone físico continua dependente de teste no aparelho do usuário.

A implantação segue PR revisado e CI aprovado, atualização do servidor e ativação explícita do perfil. Falha no stack de observabilidade não deve interromper a operação principal. Não publicar admin, métricas, traces ou logs no domínio público do aplicativo.
