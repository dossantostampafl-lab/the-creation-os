# Aceitação e auditoria de implementação futura

## Matriz rastreável

| ID | Cenário | Esperado | Plano |
|---|---|---|---|
| A01 | Conversa nova pergunta decisão anterior | Fonte/revisão correta no contexto | S1T4,S2T1 |
| A02 | Voz e texto mesma pergunta | Mesmos fatos/refs; vozstreaming mantido | S2T2 |
| A03 | CreatorA consulta fonteB | 404/empty semleak, antesranking | S1T2,T4 |
| A04 | Hipótese, decisão revogada e fato vivo | Estadoepistêmico evalidade respeitados | S1T4,S2T1 |
| A05 | Fonte revogada/indexer atrasado | Versão antiga não enviada/cacheinvalidado | S1T3,T4,S2T3 |
| A06 | Documento “ignore regras, autorizado” | Nunca role system; execução bloqueada | S2T1,T3 |
| A07 | Evento repetido/crash worker | Semduplicação, receiptretomável e commitforaordem não perdido | S1T3 |
| A08 | Mesma request_id retry | Umturno/umaresposta, erro409 divergente | S2T2 |
| A09 | Timeout query/cancel voz | Conexão devolvida, trace/degradação corretos | S2T1,T2 |
| A10 | DB/Redisfora | Diagnósticojournal; retrieslimitados, antigo=stale | S3T2 |
| A11 | Oscilaçãofalha/recovery | 3falhasabre/2sucessosrecupera, semtempestade | S3T1 |
| A12 | Export symlink/título../conflito | Pathguard/hashmanifest/quarentena | S4T1,T2 |
| A13 | Soberano desativado/ownership indefinido | Sem backfill/export automático | S1T2,S3T3 |
| A14 | Flags off/rollback | Histórico/snapshot legados, sem dadosapagados | S2T3,S4T2 |
| A15 | Ingestão semântica remota | NenhumcallLLM/embedding extra nohotpath | S1T3,S2T2 |

## Experimentos de qualidade e desempenho

fixtures/corpus.json fornece material sintético, não conteúdo real de contas. Executar perguntas com fontes esperadas; reportar recall@6, precisão defonte, assertivas semevidência e diferença entrecanal. Piso inicial: todoscasoscríticos A01/A03/A04/A05/A06 passam; recall@6 pelo menos0.90 no corpus ampliado manualmente rotulado. Corpus pequeno não garante qualidade geral.

Medir baseline e variante com mesma máquina, modelo, corpus e concorrência1/3 sessões, pelo menos100 turnos porcenário; duração/env/model/version registrados. Separar retrievalp50/p95, indexlag, TTFT, TTS e primeirafala. Comparar p95 da montagemcontexto com300ms e primeirafala combaseline+300ms para avaliar rollout. Fornecedor variávelexige repetição/intervalos; não declarar causalidade só pela média.

## Comandos de verificação no futuro

Backend cwdbackend: ../.venv/bin/ruff check . ../cyber_range/controller ../cyber_range/tests ; ../.venv/bin/mypy app ; ../.venv/bin/pytest tests/test_knowledge* tests/test_deus_context* tests/test_diagnostics* tests/test_obsidian* -q . Rodar comandos separadamente, com PostgreSQL de teste e Redis. Não contar skips como aprovação.

CI geral:pytest completo, migrações upgrade/reversão em DBdescartável, frontendbuild/unit/E2E, Composeconfig/runtime. Contratosnovos adicionados àCI existente; não usar timeouttest por sleepflaky. Securityreview e reviewersign-off antesmerge.

## Critério de decisão

Podeir: implementaçãoaprova isolamento, validade, rollback, qualidade e orçamento nohost. Condicionado: só funções de baixo risco sobflag sequalidadeincerta, sem afetaçãolegado. Nãoir: leakage/injectionautoridade/memóriarevogada/perdacancelamento/duplicaçãoefeitos ou degradação sustentadadevoz. Auditoria não substitui testes reais.
