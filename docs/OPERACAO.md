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
