# THE CREATION OS na Oracle Cloud (grátis)

O plano **Always Free** da Oracle dá uma máquina virtual permanente, sem custo, que roda o projeto inteiro (site, API, worker, Postgres e Redis) com HTTPS automático. O cartão de crédito é pedido só para verificar identidade. As regras do plano gratuito mudam de tempos em tempos, então confira as atuais no site da Oracle.

## Instalação em um comando

Depois de criar uma VM Ubuntu e liberar as portas 80 e 443 na Oracle, entre por SSH e cole **somente este comando**:

```bash
curl -fsSL https://raw.githubusercontent.com/dossantostampafl-lab/the-creation-os/main/deploy/oracle/bootstrap-oracle.sh | sudo bash
```

O bootstrap instala os pré-requisitos mínimos, clona o repositório oficial em `/opt/the-creation-os` (ou atualiza uma instalação existente para a `main`) e chama o instalador Oracle auditado. Segredos não são embutidos no comando nem no GitHub: o instalador cria as credenciais locais e mantém o `.env` somente no servidor.

## 1. Criar a conta
1. Acesse **cloud.oracle.com** e crie uma conta Free Tier.
2. Escolha a **região principal** com cuidado, porque ela não muda depois. Pegue a mais próxima de você (por exemplo, *Brazil East (São Paulo)*).

## 2. Criar a máquina
1. Vá em **Compute → Instances → Create instance**.
2. **Image:** Ubuntu 24.04 (ou 22.04).
3. **Shape:** *Ampere* → `VM.Standard.A1.Flex`, com **2 OCPUs e 12 GB** de memória. Isso cabe no gratuito; o limite é 4 OCPUs e 24 GB no total.
   - Se aparecer *"Out of capacity"*, tente outro *availability domain* ou tente mais tarde. A Oracle libera máquinas ARM aos poucos.
   - Plano B: `VM.Standard.E2.1.Micro` (AMD, 1 GB). Também é gratuita e funciona, porque o script cria memória extra (swap), mas é bem mais lenta.
4. **SSH keys:** clique em *Save private key* e guarde o arquivo `.key`.
5. Confirme que *Assign a public IPv4 address* está marcado e crie a máquina.
6. Anote o **Public IP address** que aparece.

## 3. Liberar as portas 80 e 443
1. Na página da máquina, clique na **subnet**, depois na *Security List* (Default Security List).
2. **Add Ingress Rules**, duas vezes:
   - Source CIDR `0.0.0.0/0`, IP Protocol TCP, Destination Port **80**.
   - Source CIDR `0.0.0.0/0`, IP Protocol TCP, Destination Port **443**.

O firewall interno do Ubuntu, o script abre sozinho.

## 4. Entrar na máquina
No PowerShell do Windows:
```
ssh -i C:\caminho\da\chave.key ubuntu@SEU_IP
```

## 5. Instalar
Use o mesmo comando único:

```bash
curl -fsSL https://raw.githubusercontent.com/dossantostampafl-lab/the-creation-os/main/deploy/oracle/bootstrap-oracle.sh | sudo bash
```

O primeiro build leva alguns minutos. No fim, o script mostra:
- o endereço, algo como `https://129-146-10-20.sslip.io`;
- o **usuário e a senha** do Creator, gerados na hora.

O endereço `sslip.io` é gratuito e não precisa de cadastro: ele só aponta para o IP da sua máquina, e o Caddy tira o certificado HTTPS sozinho.

## 6. Ligar a IA do DEUS
A instalação fica em `/opt/the-creation-os`. Edite:

```
sudo nano /opt/the-creation-os/.env
```

Escolha um jeito:

- **Só Claude:** `LLM_PROVIDER=anthropic`, `ANTHROPIC_API_KEY=...` e `ANTHROPIC_MODEL=...`.
- **FreeLLMAPI primeiro, Claude de reserva:**
  1. Instale o FreeLLMAPI nesta mesma máquina, seguindo o README dele. Ele precisa ouvir na porta 3001 em todas as interfaces (`0.0.0.0`), não só em `localhost`, para os containers o alcançarem. Mesmo assim, a porta continua fechada para a internet: o script só a libera para as redes internas do Docker.
  2. Configure:
     ```
     LLM_PROVIDER=freellmapi
     LLM_FALLBACK_PROVIDERS=anthropic
     FREELLMAPI_BASE_URL=http://host.docker.internal:3001/v1
     ```
  3. Preencha também as chaves `FREELLMAPI_*` e `ANTHROPIC_*`.

  **Pelo navegador (sem editar o `.env` à mão):** se o seu FreeLLMAPI usa chave, cadastre em *Settings → Secrets and variables → Actions* o segredo `FREELLMAPI_API_KEY` (a chave `freellmapi-…` gerada por ele); **se ele não tem chave, não cadastre nada**: as chamadas saem sem cabeçalho `Authorization`. Cadastre, se quiser, `FREELLMAPI_MODEL` (padrão `auto`) e `FREELLMAPI_BASE_URL` (padrão `http://host.docker.internal:3001/v1`). Depois rode *Actions → Deploy → Run workflow → task `set-inference-freellmapi`*. A tarefa configura o FreeLLMAPI como primário e a Anthropic como reserva, reinicia `api` e `worker` e mostra o que a API passou a reportar.

  A tarefa **recusa e não muda nada** se a reserva (Anthropic) não tiver `ANTHROPIC_API_KEY` e `ANTHROPIC_MODEL` no `.env` do servidor, porque a API não sobe com um provider da cadeia sem configuração. Se o FreeLLMAPI ainda não estiver instalado ou ouvindo na porta 3001, o sistema continua funcionando pela Anthropic (a reserva assume) e o relatório mostra o FreeLLMAPI como indisponível. Se o FreeLLMAPI recusar a chamada (401/403, por exemplo porque ele exige chave e nenhuma foi enviada), a reserva também assume, mas isso **esconde um erro real**: procure no log do `api` a linha `inference provider freellmapi refused its credential` (tarefa `logs`). A reserva assume quando ele está fora do ar, inacessível, estoura o tempo, está sem cota (429), responde 5xx ou recusa a credencial. Depois de rodar a tarefa, confira no relatório que o FreeLLMAPI aparece como `available: True`.

Para voltar a só Claude: task `set-inference`, que também limpa a reserva.
  4. **Não abra a porta 3001** na Security List. Para usar o painel do FreeLLMAPI, faça um túnel pelo SSH e abra `http://localhost:3001` no seu PC:
     ```
     ssh -i C:\caminho\da\chave.key -L 3001:localhost:3001 ubuntu@SEU_IP
     ```
- **Voz (opcional):** `ELEVENLABS_ENABLED=true` e `ELEVENLABS_API_KEY=...`.

Até a IA estar configurada, o site abre normalmente, mas o DEUS fica desativado e o worker reinicia em ciclo. Isso é esperado.

Salve (Ctrl+O, Enter, Ctrl+X) e rode o mesmo bootstrap novamente:

```bash
curl -fsSL https://raw.githubusercontent.com/dossantostampafl-lab/the-creation-os/main/deploy/oracle/bootstrap-oracle.sh | sudo bash
```

## Dia a dia
| Para | Comando |
| --- | --- |
| Atualizar para a versão nova | `curl -fsSL https://raw.githubusercontent.com/dossantostampafl-lab/the-creation-os/main/deploy/oracle/bootstrap-oracle.sh \| sudo bash` |
| Ver os logs | `cd /opt/the-creation-os && sudo docker compose -f docker-compose.yml -f docker-compose.cloud.yml logs -f --tail 100` |
| Parar | `cd /opt/the-creation-os && sudo docker compose -f docker-compose.yml -f docker-compose.cloud.yml down` |
| Backup do banco | `cd /opt/the-creation-os && sudo docker compose exec -T postgres pg_dump -U postgres the_creation_os > backup.sql` |

### O servidor aguenta execução privilegiada do Security Task Force?

No GitHub, **Actions → Deploy → Run workflow → task `stf-host-check`**. É somente-leitura: mostra arquitetura, tipo de máquina (shape), virtualização, `/dev/kvm`, Kata e Firecracker, e termina com o veredito de `deploy/stf/verify-host.sh`. Nada é instalado.

Uma VM comum da Oracle normalmente **não** expõe KVM (só os bare metal `BM.*`), e nesse caso o veredito é "execução privilegiada desligada". O restante do Task Force (autorização, auditoria, Range isolado) não depende disso.

## Domínio próprio (opcional, grátis)
Crie um nome em **duckdns.org** apontando para o IP da máquina e rode:

```bash
curl -fsSL https://raw.githubusercontent.com/dossantostampafl-lab/the-creation-os/main/deploy/oracle/bootstrap-oracle.sh | sudo CREATION_DOMAIN=seunome.duckdns.org bash
```

## Segurança
- O bootstrap aceita por padrão somente Ubuntu e usa o repositório oficial e a branch `main`.
- O site roda em modo produção. Só o usuário e a senha que o script gerou podem criar o Creator, e depois disso a conta fica fixada (`SOVEREIGN_CREATOR_ID`).
- O `.env` guarda todas as chaves e fica legível só pelo administrador. Não o envie para o GitHub.
- Na internet, só as portas 80 e 443 ficam abertas. API, Postgres, Redis e FreeLLMAPI ficam fechados dentro da máquina.
- A Oracle pode recuperar máquinas gratuitas que ficam **ociosas** por muito tempo. Se isso acontecer, recrie a máquina e restaure o backup.
