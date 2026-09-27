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
alias dc='sudo docker compose -f ~/the-creation-os/docker-compose.yml -f ~/the-creation-os/docker-compose.cloud.yml --project-directory ~/the-creation-os'
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
sudo grep -E '^(APP_ENV|LLM_PROVIDER|ANTHROPIC_MODEL|CREATION_DOMAIN)=' ~/the-creation-os/.env
echo "chave: $(sudo grep -c '^ANTHROPIC_API_KEY=.\+' ~/the-creation-os/.env)"
```

A segunda linha imprime `1` ou `0` sem revelar a chave.

### Ligar a inferência

Uma instalação nova sobe com `LLM_PROVIDER=fake`, que não atende missão nenhuma. Para apontá-la
a um provedor de verdade, um comando:

```
sudo ~/the-creation-os/deploy/oracle/set-inference.sh
```

Ele pede a chave com o eco do terminal desligado — a chave não aparece na tela nem entra no
histórico do shell — grava as três variáveis no `.env`, recria `api` e `worker`, e no fim imprime
o que a própria API responde. É o que vale: `configured: true` com o provedor e `available: true`.

O padrão é `anthropic` com `claude-sonnet-5`. Para outro provedor ou modelo:

```
sudo ~/the-creation-os/deploy/oracle/set-inference.sh anthropic claude-sonnet-5
sudo ~/the-creation-os/deploy/oracle/set-inference.sh openai gpt-4o-mini
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
sudo ~/the-creation-os/deploy/oracle/set-creator-password.sh
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
sudo ~/the-creation-os/deploy/oracle/check-inference.sh
```

Ele responde três perguntas em ordem, porque a resposta errada em uma explica a seguinte: o que o
`.env` guarda, o que o contêiner em execução recebeu dele, e o que a API responde. A chave só
aparece como contagem de caracteres. Um `.env` certo com um contêiner vendo outra coisa significa
que `api` e `worker` não foram recriados depois da troca.

### Trocar qualquer outro valor

Para trocar um valor sem abrir editor, e sem deixar o segredo no histórico do shell:

```
D=~/the-creation-os; V=ANTHROPIC_API_KEY
read -rsp "Cole o valor e Enter: " K; echo "  (${#K} caracteres)"
sudo cp "$D/.env" "$D/.env.bak"
sudo grep -vE "^$V=" "$D/.env" | sudo tee "$D/.env.novo" >/dev/null
printf '%s=%s\n' "$V" "$K" | sudo tee -a "$D/.env.novo" >/dev/null
sudo mv "$D/.env.novo" "$D/.env"; sudo chown root:root "$D/.env"; sudo chmod 600 "$D/.env"; unset K
dc up -d --force-recreate api worker
```

Não use `sed` para isto. O valor entraria dentro da expressão `s|...|...|`, e uma chave que
contenha o delimitador `|` faz o `sed` parar com ``unknown option to `s'`` sem escrever nada —
o `.env` fica intacto e parece que deu certo. O `printf '%s'` acima grava o valor como texto
puro, e o `grep -v` seguido do append funciona tanto se a linha já existir quanto se faltar
(o `sed` só substituía linhas existentes; se a variável não estivesse no arquivo, não fazia nada).
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
sudo git -C ~/the-creation-os fetch origin main
sudo git -C ~/the-creation-os reset --hard origin/main
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

### Os segredos, configurados uma vez

Em **Settings → Secrets and variables → Actions → New repository secret**:

| Segredo | Obrigatório | O que é |
|---|---|---|
| `DEPLOY_SSH_KEY` | sim | O conteúdo do arquivo `.key` do Oracle, inteiro, incluindo as linhas `-----BEGIN` e `-----END`. |
| `DEPLOY_HOST` | sim | O IP público do servidor. |
| `DEPLOY_USER` | não | O usuário do SSH. Sem ele, `ubuntu`. |
| `DEPLOY_REPO_DIR` | não | O caminho do projeto no servidor. Sem ele, `~/the-creation-os`. |
| `DEPLOY_SSH_HOST_KEY` | não | Só para um servidor cujas chaves não estejam em `deploy/oracle/known_hosts`. |
| `ANTHROPIC_API_KEY` | só para `set-inference` | A chave da Anthropic. |
| `ANTHROPIC_MODEL` | não | Sem ele, `claude-sonnet-5`. |
| `ANTHROPIC_WORKSPACE_ID` | depende | Obrigatório se a chave for da organização, não presa a um Workspace. |
| `CREATOR_PASSWORD` | só para `set-creator-password` | A senha que você quer para entrar na interface. |

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
