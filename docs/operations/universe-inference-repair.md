# Reparação da inferência dos universos

## Causa observada em 2026-10-05

O sistema estava configurado com FreeLLM como primário, mas os 12 agentes canônicos mantinham `inference_provider=anthropic`, gravado pelo seed anterior. O runtime das tarefas respeitava esse campo: as tentativas retornavam erro upstream do Anthropic e as tentativas seguintes encontravam o circuito aberto. A consulta de disponibilidade da API não comprovava a geração usada pelos agentes.

O diagnóstico dentro da API e do worker confirmou configuração e endpoint FreeLLM iguais e geração sintética HTTP 200, com e sem a definição de ferramenta. Os 12 perfis eram perfis gerados reconhecíveis, sem personalizações adicionais. Nenhum texto de resposta, conversa ou credencial foi registrado pelo diagnóstico.

## Comportamento corrigido

Perfis gerados recebem `inference_routing=configured`. Tarefas e geração de teses de oportunidades usam a cadeia atual do runtime para esses perfis. Modelos ou fallbacks explicitamente fixados permanecem autoritativos. Para fixar manualmente também o provedor de um perfil gerado, use `inference_routing=pinned`.

A reparação reconhece somente perfis canônicos gerados, atuais ou antigos com descrição e provedor. Mantém os campos personalizados, agentes/universos pausados, autorizações, grants e missões existentes. Registra as mudanças na Chronicle e é idempotente. Recusa executar sem um Creator soberano ativo resolvido sem ambiguidade.

## Aplicação e verificação

Após CI e implantação da versão corrigida:

1. Execute **Deploy → repair-universe-inference**, `ref=main`, para atualizar somente a configuração reconhecida dos agentes. Não use o seed geral como substituto: ele também pode reativar agentes e universos.
2. Execute **Deploy → check-universe-inference** para comparar configuração e geração sintética nos dois processos. O diagnóstico usa quatro perguntas curtas ao FreeLLM; não cria missões nem chama ferramentas.
3. Execute **Deploy → browser-gauntlet** para criar e executar novas missões internas de teste, incluindo tarefas dos 12 universos. As missões anteriormente falhadas permanecem no histórico; não são reautorizadas silenciosamente.

Uma resposta 200 em `/models` não comprova a geração. Observe o resultado da missão, o provedor efetivamente utilizado e os spans `llm.attempt`/`agents.task` no stack privado de observabilidade.
