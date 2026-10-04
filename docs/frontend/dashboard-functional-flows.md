# Fluxos funcionais do dashboard

## Cyber Range privado

O painel de memória e Cyber Range lista os dez agentes canônicos, seu registro e estado ativo/pausado, além dos últimos ciclos reais. “Pausar” impede a seleção para novos ciclos; não cancela o ciclo em execução. “Retomar” permite a seleção novamente. O worker não desfaz uma pausa escolhida pelo Criador.

“Treinar” solicita um ciclo da campanha fixa `stf-advanced-v1` no ambiente `cyber_range:lab-a`. A API exige sessão do Criador, worker habilitado e controlador acessível. O agendador automático e os pedidos manuais usam a mesma serialização PostgreSQL; há apenas uma campanha ativa no laboratório compartilhado. Nenhum controle autoriza alvos públicos. Um agente pausado não pode receber um pedido manual de novo ciclo.

Endpoints: `GET /api/v1/cyber-range/training`, `POST /api/v1/cyber-range/training/start` com `agent_code` canônico. Pausa e retomada reutilizam `/agents/{id}/deactivate` e `/agents/{id}/activate`. Atualize a lista para observar as mudanças de execução; `QUEUED` significa enfileirado, não concluído.

## Missões

No painel de decisões, “Criar missão” abre o planejamento manual. O Criador fornece título, objetivo, estratégia e etapas sequenciais atribuídas aos universos ativos. O fluxo guarda a mensagem de origem, cria e aprova a inception, cria a missão, salva o plano e o valida. O início requer confirmação separada e mantém as verificações de autorização existentes.

A lista permite consultar missões e tarefas reais, incluindo tentativas e erros. O rascunho e os identificadores persistem em `sessionStorage` para retomar falhas temporárias. O logout remove o rascunho. Não se usa geração de plano por provedor pago.

## Downloads Android

O painel mostra apenas artefatos publicados e verificados. O download usa a sessão autenticada e verifica tamanho e SHA-256 no navegador. Debug é para testes. APK e AAB release gerados sem chave de produção continuam sem assinatura de distribuição; não são uma publicação nas lojas.

O host monta `./releases` somente para leitura no serviço API, como `/var/lib/creation/releases`. Pode-se alterar o diretório com `RELEASE_ARTIFACTS_DIR` e um mount correspondente. Nunca guardar artefatos no Git.

Publicação automatizada: workflow **Deploy**, tarefa **publish-builds**, ref desejado. A tarefa compila os três arquivos do ref, gera manifesto com SHA do commit e publica no diretório `releases` do checkout usado pelo servidor. O deploy da aplicação com o novo mount deve ocorrer primeiro. Essa tarefa não reinicia serviços.

Publicação manual:

```sh
# staging deve conter creation-debug.apk, creation-release-unsigned.apk e creation-release.aab
node frontend/scripts/create-build-manifest.mjs staging COMMIT_SHA
bash deploy/oracle/publish-builds.sh staging /caminho/do/checkout/releases
```

Versões são imutáveis; uma versão já publicada não é sobrescrita. O manifesto atual é trocado atomicamente depois da cópia e validação. Arquivos ausentes ou corrompidos geram erro explícito, sem link de download. Os endpoints exigem sessão do Criador: `GET /api/v1/builds` e `GET /api/v1/builds/{artifact_id}/download`.

## DEUS e validação

Turnos conversacionais com o construtor de contexto reutilizam sua leitura de agentes, universos e missões, evitando uma segunda leitura. Pedidos que precisam de Trinity preservam a percepção necessária. Isso reduz trabalho de banco; a duração completa ainda depende da inferência disponível.

O smoke do deploy verifica três turnos com conteúdo: preferência de voz, recuperação dessa preferência no contexto e obediência a uma resposta curta especificada. Registra a duração de cada turno e falha em incoerência; apenas receber texto não basta. A qualidade do timbre e a captura do microfone precisam também de avaliação no dispositivo real.

Validação local desta implementação: 902 testes backend passaram, com oito skips por capacidades ausentes no ambiente; 63 testes Chromium, 43 testes unitários frontend, Ruff, mypy em 199 módulos, build frontend e Android, assinatura do APK debug e configuração Compose passaram. A publicação e a medição no servidor são etapas distintas destes checks locais.
