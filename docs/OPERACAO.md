# Operação do servidor

Comandos para operar a instalação em produção na Oracle Cloud. Escrito para ser lido no celular,
no meio de um problema.

## Onde você está

O erro mais caro desta operação não é técnico: é rodar o comando certo na máquina errada. O Cloud
Shell da Oracle, um Codespace do GitHub e o servidor são três máquinas diferentes, e duas delas
têm uma cópia do repositório. Antes de qualquer coisa:

```
hostname
```

Se não responder `the-creation-os`, você não está no servidor. Entre nele:

```
ssh -i ~/ssh-key-*.key ubuntu@<ip-publico-da-vm>
```

## O atalho

O comando do Compose é longo e precisa dos dois arquivos, o base e o da nuvem. Este atalho carrega
os dois e funciona de qualquer pasta, porque diz ao Docker onde o projeto mora:

```
alias dc='sudo docker compose -f /opt/the-creation-os/docker-compose.yml -f /opt/the-creation-os/docker-compose.cloud.yml --project-directory /opt/the-creation-os'
```

Ele vale só na sessão atual; quando a conexão cair, crie de novo. Sem o `--project-directory`, o
Docker procura os arquivos na pasta em que você está e falha com "no such file or directory".

## Ver o estado

```
dc ps
dc logs --tail=50 api
dc logs -f worker
dc logs --tail=30 caddy
```

`Ctrl+C` sai do `-f`, que fica acompanhando.

## Ligar, desligar, reiniciar

```
dc up -d
dc up -d --force-recreate api worker
dc restart api
dc down
```

`dc down` para os contêineres e **não apaga dados** — o banco, os snapshots e as evidências ficam
nos volumes. Nunca use `down -v`: essa variante apaga os volumes.

## Configuração

O `.env` fica na raiz do projeto, ao lado do `docker-compose.yml`. Ele pertence ao root e tem
permissão 600, então precisa de `sudo` para ler. O `.env.example` é só o modelo versionado; nada
em execução o lê, e ele permanece com valores `fake` de propósito.

```
sudo grep -E '^(APP_ENV|LLM_PROVIDER|ANTHROPIC_MODEL|CREATION_DOMAIN)=' /opt/the-creation-os/.env
echo "chave: $(sudo grep -c '^ANTHROPIC_API_KEY=.\+' /opt/the-creation-os/.env)"
```

A segunda linha imprime `1` ou `0` sem revelar a chave.

### Ligar a inferência

Uma instalação nova sobe com `LLM_PROVIDER=fake`, que não atende missão nenhuma. Para apontá-la
a um provedor de verdade, um comando:

```
sudo /opt/the-creation-os/deploy/oracle/set-inference.sh
```

Ele pede a chave com o eco do terminal desligado — a chave não aparece na tela nem entra no
histórico do shell — grava as três variáveis no `.env`, recria `api` e `worker`, e no fim imprime
o que a própria API responde. É o que vale: `configured: true` com o provedor e `available: true`.

O padrão é `anthropic` com `claude-sonnet-5`. Para outro provedor ou modelo:

```
sudo /opt/the-creation-os/deploy/oracle/set-inference.sh anthropic claude-sonnet-5
sudo /opt/the-creation-os/deploy/oracle/set-inference.sh openai gpt-4o-mini
```

O `.env` anterior fica guardado como `.env.bak` ao lado dele.

Para `anthropic` ele também pergunta um **Workspace ID**. Se a sua chave foi criada dentro de um
Workspace, ela já o carrega consigo e basta apertar Enter. Se ela é da organização — não presa a
um Workspace — a Anthropic **exige** o header, e sem ele toda chamada volta assim:

```
HTTP 400  invalid_request_error
This API key is not scoped to a workspace, so this request must include the
anthropic-workspace-id header with the ID of the workspace to use.
```

Nesse caso o `check-inference.sh` mostra `configured: true` com `available: false` e
`upstream_status_400`, e a seção 4 dele imprime a mensagem acima na íntegra. Se o ID enviado não
for o da chave, a API também recusa. Quando precisar, ele tem a forma `wrkspc_011CZkZaBF1tNoB5wlCeusgy`, e sai em
`console.anthropic.com` → Settings → Workspaces, na barra de endereço ao abrir o Workspace.

### Trocar a senha do Criador

```
sudo /opt/the-creation-os/deploy/oracle/set-creator-password.sh
```

Pede a senha duas vezes, sem mostrar na tela, grava no `.env`, recria `api` e `worker` — a API só
lê o `.env` quando o contêiner nasce, então a rotação sem a recriação trocaria para o valor
antigo — roda o `rotate-creator-password`, e no fim confirma entrando com a senha nova. Toda
sessão aberta com a senha anterior é encerrada; isso faz parte da troca, não é um extra.

Mínimo de 12 caracteres, máximo de 72 **bytes** (um acento custa dois: o bcrypt lê só os
primeiros 72 e ignora o resto em silêncio), e sem quebra de linha.

Pelo navegador: guarde a senha escolhida como o segredo `CREATOR_PASSWORD` e rode a tarefa
`set-creator-password` no workflow Deploy.

### Conferir como está

Um comando de leitura, que não altera nada:

```
sudo /opt/the-creation-os/deploy/oracle/check-inference.sh
```

Ele responde três perguntas em ordem, porque a resposta errada em uma explica a seguinte: o que o
`.env` guarda, o que o contêiner em execução recebeu dele, e o que a API responde. A chave só
aparece como contagem de caracteres. Um `.env` certo com um contêiner vendo outra coisa significa
que `api` e `worker` não foram recriados depois da troca.

### Trocar qualquer outro valor

Para trocar um valor sem abrir editor, e sem deixar o segredo no histórico do shell:

```
D=/opt/the-creation-os; V=ANTHROPIC_API_KEY
read -rsp "Cole o valor e Enter: " K; echo "  (${#K} caracteres)"
if [[ "$V" =~ ^[A-Z_][A-Z0-9_]*$ ]]; then
  sudo cp "$D/.env" "$D/.env.bak"
  printf '%s' "$K" | sudo bash -c '
    set -euo pipefail
    cd "$1"
    source deploy/oracle/env-file.sh
    value="$(cat)"
    env_set "$2" "$value"
  ' _ "$D" "$V" && dc up -d --force-recreate api worker
else
  echo "Nome de variável inválido" >&2
fi
unset K
```

Não use `sed`, regex ou append manual para isto. O comando acima entrega o valor pela entrada
padrão, portanto o segredo não aparece nos argumentos do processo, e chama o único gravador
permitido, `env_set`. Ele escreve o valor literalmente, cria a variável se faltar, elimina linhas
duplicadas e recusa quebras de linha antes que elas possam injetar outra variável no `.env`.
O `${#K}` imprime só o tamanho, para você conferir que o paste não veio cortado.

A API só lê o `.env` quando o contêiner nasce, então a recriação é parte da troca, não um extra.

## Comandos administrativos

```
dc exec api seed-universes
dc exec api rotate-creator-password
dc exec api restore-creator
```

- `seed-universes` cria os Universes e seus Agents. É idempotente: rodar de novo não duplica nada.
  Sem ele, o ROCKMAM julga toda missão inviável, porque não há Universe para executá-la.
- `rotate-creator-password` dá ao Criador a senha que está no `.env` e **encerra todas as sessões
  abertas**. A ordem importa: edite o `.env`, recrie a API, então rode. Ele recusa se o `.env` não
  mudou.
- `restore-creator` só age quando o Criador configurado não existe; serve para recuperar a
  identidade, não para trocar senha.

## Atualizar o código

```
sudo git -C /opt/the-creation-os fetch origin main
sudo git -C /opt/the-creation-os reset --hard origin/main
dc up -d --build
```

O `.env` sobrevive ao `reset --hard` porque não é versionado. Os dados também, porque vivem em
volumes.

## Conferir de fora

```
https://<dominio>/
https://<dominio>/api/v1/health/ready
```

O segundo responde `{"status":"ready"}` somente quando a API alcança o banco **e** o Redis, então
ele vale mais que um simples "o site abriu".

## O que não fazer nesta máquina

`deploy/oracle/bootstrap-oracle.sh` instala em `/opt/the-creation-os` e cria um `.env` novo, com
chave de assinatura e senha de Criador geradas do zero. Numa VM que já tem instalação, isso produz
um segundo checkout e credenciais que não conferem com o banco existente. Esse script é para
servidor novo.

## Operar pelo navegador, sem terminal

Há um workflow `Deploy` na aba **Actions** do repositório. Ele existe para que manter o servidor
não dependa de abrir um terminal: você escolhe a tarefa e aperta um botão.

**Ele só roda quando alguém aperta o botão.** Nenhum `push` o dispara, de propósito — um commit
não pode alcançar o servidor.

### As quatro tarefas

| Tarefa | O que faz |
|---|---|
| `check` | Só lê e informa: o que o `.env` guarda, o que o contêiner recebeu, o que a API responde. Não altera nada. |
| `restart` | Recria `api` e `worker`, que é como eles releem o `.env`, e depois informa. |
| `update` | Traz o código novo, reconstrói tudo e informa. |
| `set-inference` | Grava a chave que está nos segredos do repositório e recria `api` e `worker`. |
| `set-creator-password` | Dá ao Criador a senha guardada no segredo `CREATOR_PASSWORD` e encerra as sessões abertas. |
| `tidy` | Relata todas as cópias do projeto no servidor. Não move nada; só informa. |
| `logs` | Últimas linhas dos logs do `api` e do `worker`, com segredos mascarados. |
| `set-voice` | Liga a voz do DEUS no ElevenLabs e confirma com a própria ElevenLabs. |
| `smoke-test` | Exercita o app inteiro por dentro e diz o que passou e o que falhou. |
| `seed` | Semeia os 12 Universos canônicos e seus Agents, e mostra o resultado. |

### Os segredos, configurados uma vez

Em **Settings → Secrets and variables → Actions → New repository secret**:

| Segredo | Obrigatório | O que é |
|---|---|---|
| `DEPLOY_SSH_KEY` | sim | O conteúdo do arquivo `.key` do Oracle, inteiro, incluindo as linhas `-----BEGIN` e `-----END`. |
| `DEPLOY_HOST` | sim | O IP público do servidor. |
| `DEPLOY_USER` | não | O usuário do SSH. Sem ele, `ubuntu`. |
| `DEPLOY_REPO_DIR` | recomendado | Defina como `/opt/the-creation-os`. Sem ele, uma recuperação com o contêiner `api` parado não consegue descobrir com segurança o diretório canônico. |
| `DEPLOY_SSH_HOST_KEY` | não | Só para um servidor cujas chaves não estejam em `deploy/oracle/known_hosts`. |
| `ANTHROPIC_API_KEY` | só para `set-inference` | A chave da Anthropic. |
| `ANTHROPIC_MODEL` | não | Sem ele, `claude-sonnet-5`. |
| `ANTHROPIC_WORKSPACE_ID` | depende | Obrigatório se a chave for da organização, não presa a um Workspace. |
| `CREATOR_PASSWORD` | só para `set-creator-password` | A senha que você quer para entrar na interface. |
| `ELEVENLABS_API_KEY` | só para `set-voice` | A chave da ElevenLabs. |
| `ELEVENLABS_VOICE_ID` | só para `set-voice` | O ID da voz, 20 letras e dígitos. |

### O que isso significa em segurança

A partir do momento em que `DEPLOY_SSH_KEY` está ali, **quem puder disparar workflows neste
repositório alcança o servidor**. Com o repositório privado e um único dono, o risco é pequeno.
Se houver mais gente com acesso de escrita, vale mover os segredos para um *Environment* com
revisor obrigatório, em Settings → Environments.

### A identidade do servidor

As chaves públicas de host do servidor estão em `deploy/oracle/known_hosts`, e o workflow as usa
em toda execução. Se outro computador responder no lugar do seu servidor, o deploy **para** em vez
de entregar a chave SSH a ele. Não há segredo a criar: chave de host é pública por definição — é o
que o servidor mostra a todo cliente que conecta — então ela fica no repositório, onde pode ser
lida e conferida, ao contrário de um segredo que ninguém consegue reler.

O endereço fica guardado em forma de hash, do mesmo jeito que o `HashKnownHosts` do OpenSSH grava,
então ele não é legível ali.

Se um dia você recriar a instância do Oracle, as chaves mudam e todo deploy passa a recusar a
conexão. Isso é o comportamento certo: substitua o arquivo pela saída do `ssh-keyscan` do servidor
novo, deliberadamente.

### As cópias do projeto no servidor

O Compose tira o nome do projeto do nome da pasta, e toda cópia deste projeto se chama
`the-creation-os`. Duas cópias, portanto, apontam para os **mesmos** contêineres e os **mesmos**
volumes: um `docker compose down -v` digitado na pasta errada levaria o banco junto.

A tarefa `tidy` relata todas as cópias e qual delas está servindo. Ela não apaga nada; com
`--park`, o script move as paradas para `<pasta>.parked-<data>`, o que dá a elas um nome de
projeto próprio e desfaz a armadilha. Um `mv` reverte. Uma pasta iniciada por um serviço do
systemd ou por um cron não é movida.

## A voz do DEUS

A voz usa apenas a sessão de tempo real em `/api/v1/voice/session`, com STT
`scribe_v2_realtime` e TTS ElevenLabs em streaming. Sem configuração, a sessão informa o erro;
a entrada por texto continua disponível. Não há reconhecimento ou síntese de voz do navegador.

O `.env.example` vem com `ELEVENLABS_ENABLED=false`. Para ligar a voz, guarde
`ELEVENLABS_API_KEY` e `ELEVENLABS_VOICE_ID` nos segredos do repositório e rode a tarefa
`set-voice`. O workflow configura `KLAUS_PROVIDER=anthropic`, a reserva Claude confirmada.

O script verifica o nome da voz quando a chave permite consultá-lo e testa o mesmo cliente
WebSocket TTS usado pela aplicação. O sucesso imprime bytes PCM em tempo real; a consulta do
nome sozinha não comprova que a síntese funciona. Rode `smoke-test` para verificar também o
áudio de confirmação, o ticket, a abertura da sessão e a conversa com o DEUS.

O ID da voz sai em `elevenlabs.io` → Voices → a voz → o identificador de 20 caracteres.

## Testar o app inteiro

```
sudo /opt/the-creation-os/deploy/oracle/smoke-test.sh --deus
```

Ou a tarefa `smoke-test` no workflow Deploy.

Ele entra como Criador e percorre o que cada parte da interface depende: universos, agentes,
missões, inceptions, conversas, Chronicle e sua integridade, pulse, estado do sistema, projeções,
cache, a projeção de oportunidades, a inferência, o áudio de confirmação, a sessão de voz em tempo real e uma conversa com o DEUS.
No fim, quantos passaram e quantos falharam.

Ele roda **dentro do contêiner da API**, então as credenciais que usa são as que já estão no
ambiente daquele processo: nada viaja por linha de comando, onde a lista de processos do servidor
mostraria.

Duas linhas do relatório valem mais que as outras quando algo parece quebrado na tela:

- **`a provider is available`** é exatamente a expressão que a interface usa para habilitar o
  console do DEUS. Falhando ela, o campo de mensagem fica inerte e o microfone não responde — sem
  erro nenhum aparecer, porque o envio simplesmente retorna.
- **`ElevenLabs wake acknowledgement`** verifica o áudio PCM de confirmação; **`realtime DEUS
  voice session`** verifica a conexão autenticada e o estado `ARMED`. Falhas precisam ser
  corrigidas na configuração ou nos provedores. O smoke não mede eco ou latência num aparelho
  físico; valide também no Android falando “Deus”, conversando e interrompendo a resposta.

## Os Universos não vêm com o deploy

Um deploy traz código, nunca linhas no banco. Quando o PR #69 levou os 12 Universos canônicos ao
servidor, o banco continuou com os 4 que já tinha — e um pedido fora deles o ROCKMAM julga
inviável, então o DEUS não tem o que propor e parece "não saber o que fazer".

A tarefa `seed` resolve. O seeder é idempotente: ele reconcilia os 12 sem duplicar os que já
existem, e no fim o relatório mostra a contagem.

Confira em `smoke-test` a linha `universes`. Se disser menos que 12, é isso.
