# Evidências de validação

- Backend: 947 testes aprovados, oito pulados no ambiente local; Ruff e mypy aprovados (202 módulos). Um teste de reinício Temporal travou numa execução e passou isoladamente e na repetição completa (126 s); a causa do travamento não foi confirmada.
- SDK: filtragem de atributos, nome/status/recursos/tracestate, resultado preservado quando a coleta está desligada, falhas do exporter, streaming/cancelamento e inicialização real com exporter indisponível.
- HTTPX→FastAPI→Collector→Tempo: trace distribuído consultado; parâmetro sintético privado ausente no resultado.
- Collector: entrada OTLP deliberadamente não sanitizada perdeu payload, evento, scope, status e tracestate privados antes do Tempo.
- Collector parado: API de teste respondeu 401 em 11 ms; a exportação não bloqueou a requisição.
- Prometheus: contadores e histogramas reais consultáveis, buckets próprios para latência; node-exporter e estado agregado disponíveis.
- Promtail: dry-run reteve eventos válidos e descartou linhas privadas/malformadas. Loki real retornou somente o evento operacional permitido.
- Grafana 11.2.0: oito dashboards provisionados e consultas às três fontes. A validação local executou Grafana pelo binário oficial para evitar a duplicação de camadas do driver Docker VFS.
- Tempo/Loki: inicialização e escrita com volumes Docker reais, sem permissões especiais de tmpfs.
- Revisão independente: quatro achados corrigidos (filtro legado, segunda sanitização, readiness e amostragem da verificação); re-revisão sem problemas importantes restantes.

A confirmação de CI, ativação do servidor e Gauntlet de produção será registrada após a implantação. A captura pelo microfone físico continua pendente no aparelho do usuário.
