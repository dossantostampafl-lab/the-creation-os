# Operar a observabilidade

P0 e P1 usam serviços locais e não exigem créditos de provedores. A telemetria vem desativada no `.env.example`. No GitHub, execute **Deploy → enable-observability**, com `ref=main`, após CI e integração. O script reconstrói os processos com o SDK, preserva os perfis já habilitados e valida o caminho real por meio do proxy autenticado do Grafana.

## Acesso privado

Grafana é o único serviço com porta publicada: `127.0.0.1:3300` por padrão. Para acessar a instalação Oracle, use `ssh -L 3300:127.0.0.1:3300 usuario@servidor` e abra `http://localhost:3300`. Se `STF_GRAFANA_PORT` já estiver definido, substitua a porta de destino por esse valor. Usuário inicial: `admin`. A senha fica em `STF_GRAFANA_ADMIN_PASSWORD` no `.env` protegido do servidor; o script preserva a existente e gera uma senha forte somente quando ausente. Não publique essa senha ou o Grafana no domínio do aplicativo.

Collector, Tempo, Prometheus, Loki e node-exporter não publicam portas. Não há rota pública para `/metrics`, logs ou traces. Tempo, Prometheus, Loki e Grafana possuem volumes próprios. A instalação precisa de espaço para imagens, volumes e retenção; reserve capacidade adicional antes de habilitar o perfil. Prometheus mantém até sete dias/2 GB de blocos (WAL requer espaço adicional); Tempo e Loki possuem retenção de sete dias.

## O que observar

Os oito dashboards ficam na pasta **Creation OS**. Volume, erros e p95 vêm das operações instrumentadas. No Voice, o painel por etapa mostra transcrição→primeiro token, primeiro token→primeiro áudio e duração total do turno; as operações STT/TTS mostram processamento e espera pela síntese, sem gravar áudio/texto. `voice.turn.step` e `llm.stream.step` medem avanços do streaming, enquanto `creation.voice.latency` mede o turno completo. A wake word possui checagens e um evento de detecção confirmado.

Agentes, Missões, Opportunity Fabric e Cyber Range mostram contagens agregadas do banco por estado. Não existe coleta de IDs, objetivos ou títulos de missões. A idade do snapshot precisa permanecer próxima ao intervalo de 30 segundos; dados antigos não comprovam saúde. O painel de infraestrutura mostra CPU/memória do host, saúde dos scrapes, recursos dos processos e exportações recentes dos workers. Coletar `/proc` e `/sys` é somente leitura, sem Docker socket.

Eventos JSON possuem `trace_id`/`span_id`. Clique no campo TraceID no Loki para consultar o Tempo. A instrumentação HTTPX propaga `traceparent` às requisições; não propaga baggage. A exportação limpa atributos, nomes, eventos, links, detalhes de exceção, recursos e tracestate. O Collector repete a filtragem de atributos, recursos, scopes e eventos; spans com links são descartados. Logs antigos não são copiados: o antigo filtro genérico STF foi removido porque podia aceitar texto arbitrário contendo `"event"`.

## Configuração e falhas

`TELEMETRY_ENABLED`, `TELEMETRY_OTLP_ENDPOINT` e `TELEMETRY_SAMPLE_RATIO` controlam o SDK. O endpoint deve ser uma origem HTTP(S) sem credenciais/query. O script usa o Collector privado. Sampling afeta traces; métricas e eventos operacionais continuam disponíveis. A verificação usa sampling=1 somente no processo sintético e não altera o valor escolhido para os processos em execução.

Fila de spans: 1024, lote: 128, exportação assíncrona, timeout HTTP: dois segundos. O Collector limita memória, fila e tentativas de envio. Uma falha de exportação não participa da resposta do chat/voz. Spans e métricas podem ser perdidos durante uma indisponibilidade; este stack não é um registro auditável de decisões de autorização.

Se o `compose up` falhar, o script restaura o `.env` salvo. Se somente a verificação falhar, mantém a instrumentação e o stack ativos para diagnóstico e retorna falha ao workflow. Examine `docker compose --profile observability logs --tail=100 otel-collector tempo prometheus stf-loki stf-promtail stf-grafana`, sem publicar logs privados ou o `.env`. Corrija disponibilidade, credenciais ou espaço e execute novamente a ativação. A API possui uma espera de readiness antes do teste e a verificação aguarda até 90 segundos por traces, métricas, logs, dashboards, infraestrutura e snapshot.

Para interromper a coleta: defina `TELEMETRY_ENABLED=false` no `.env` e recrie API/workers com seus perfis atuais. Pare apenas os serviços de observabilidade quando não precisar mais das consultas. Preserve os volumes para investigação; não use `down -v` na instalação. Atualizações normais mantêm o perfil quando `TELEMETRY_ENABLED=true`.

## Evidências

A validação local inclui trace distribuído HTTPX→FastAPI consultado no Tempo, série real consultada no Prometheus, evento real filtrado no Loki, oito dashboards carregados no Grafana e snapshots/infraestrutura consultáveis. O teste de privacidade insere somente marcadores sintéticos e confirma sua ausência no trace exportado; o teste do Promtail confirma que linhas privadas/malformadas são descartadas. Volumes reais de Tempo e Loki também são verificados. O Gauntlet após a implantação verifica os fluxos do aplicativo com o SDK ativo. Isso não comprova a captura pelo microfone físico do usuário.
