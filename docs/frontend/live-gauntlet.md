# Gauntlet no ambiente publicado

O ciclo é planejar, implementar, testar, auditar, simular falhas, corrigir, retestar e auditar novamente. O resultado de CI ou de health checks não substitui a conclusão dos fluxos do Creator.

No workflow manual **Deploy**, a tarefa **browser-gauntlet** usa Chromium contra o domínio configurado no servidor. Recebe por stdin somente um access token temporário e áudio sintético de QA. Não exporta senha, refresh token, perfil de navegador ou conteúdo de conversas privadas. Os registros criados têm prefixo `Gauntlet QA`; a missão de teste pede somente uma resposta textual, sem ações externas. Não há logout global, porque esse endpoint revogaria também as sessões do Creator.

O roteiro verifica:

- Dezesseis leituras pelo gateway HTTPS, com concorrência máxima de quatro.
- Dashboard autenticado e envio de pergunta com resposta coerente na interface.
- Downloads Android iniciados pelos botões e verificados por tamanho e SHA-256.
- Treinamento com ao menos uma campanha realmente `COMPLETED`.
- Criação, validação, autorização, execução e conclusão de uma missão textual de QA.
- Uma missão adicional com doze etapas sequenciais, uma por Universe ativo, sem efeitos externos. Confere doze tarefas bem-sucedidas em doze Universes distintos; não certifica autonomia em redes públicas.
- Chat após uma falha de rede simulada somente no serviço de projeções.
- Áudio sintético entrando pelo microfone do Chromium, wake word, transcrição, resposta textual e PCM retornado.

O teste sintético não certifica permissões, microfone, saída de áudio ou latência no aparelho do usuário. Arquivos Android de release ainda exigem assinatura de produção. MinIO não está configurado neste projeto; inventário de containers não certifica gravação/leitura de objetos.

## Bloqueios identificados em 5 de outubro de 2026

1. Temporal escutava apenas em uma das duas interfaces privadas; o cliente resolvia o endereço da outra. PR125 corrigiu o bind. A fila avançou depois da atualização, comprovando o primeiro bloqueio.
2. O gateway isolado não possui rota padrão. `host.docker.internal` apontava para a bridge Docker fora de suas redes. O relay passa a escutar na interface host da rede `stf-control`, mantendo token e targets privados, sem adicionar rede pública ao gateway.
3. Um ciclo abortado revogava a missão que os ciclos seguintes reutilizavam. Cada novo ciclo agora recebe sua própria missão, incluindo escopo do Creator e número do ciclo. O histórico antigo continua reconhecido. A revogação anterior, o kill switch global, pausas e exclusividade do laboratório permanecem aplicados; não há limpeza de revogações para retomar um ciclo.

Campanhas com estado não terminal, inclusive resultado desconhecido, continuam bloqueando novas campanhas. Não se repete um efeito cujo resultado seja incerto. As execuções continuam limitadas a `cyber_range:lab-a`, campanha `stf-advanced-v1`, risco máximo R2 e exclusão de `real:*`.
