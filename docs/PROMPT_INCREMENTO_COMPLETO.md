# PROMPT — Incremento completo: dashboard fiel à imagem, comando de voz em todos os elementos, e fechamento de todas as lacunas funcionais

Cole este prompt no Claude Code (ou outro agente com Docker, Node, shell e
navegador reais na sua máquina), rodando na raiz do repositório
`THE CREATION OS`. Este documento substitui e engloba
`docs/PROMPT_FRONTEND_LIVING_UNIVERSE.md` (mantenha aquele arquivo como
histórico, mas siga este).

**Antes de começar, peça ao Criador para colar a imagem de referência da
Creator Interface diretamente nesta conversa** (screenshot que ele já
mostrou antes) — você vai precisar comparar pixel a pixel, não só ler a
descrição abaixo.

---

## Decisão já tomada pelo Criador (não reabra esta discussão)

Havia uma tensão entre `ARCHITECTURE.md`/documentação anterior ("painéis
somente sob demanda, sem dashboard permanente") e a imagem de referência
(cabeçalho, cards de Universo/SOPHIA/ROCKMAM e rodapé de crônicas sempre
visíveis). **O Criador decidiu: a imagem vence.** O dashboard deve ficar
permanentemente visível, igual à imagem. Os painéis profundos (Inceptions,
Missões, Oportunidades, Capabilities, Percepção — abertos via
`requestedPanel`/`demandPanel`) continuam sob demanda como já funcionam;
isso não muda. O que muda é a camada ambiente (cabeçalho de pulso, cards de
constelação, rodapé de crônicas) — essa fica sempre visível.

## Contexto técnico já existente (não reinvente)

- `frontend/src/components/LivingDashboard.tsx` já tem `LivingUniverseScene`
  — canvas procedural real, ligado a `agents`/`universes`/`pulse` reais via
  `requestAnimationFrame`, desenhando DEUS/SOPHIA/ROCKMAM/Universos/agentes
  como pontos vivos com conexões neurais animadas. Isso já é dinâmico, não é
  imagem estática.
- `SystemPulseHeader.tsx`, `UniverseConstellationLabels.tsx` e
  `ChronicleTicker.tsx` foram criados numa sessão anterior **sem
  `npm run build` rodando** (sandbox sem Docker/rede) — foram escritos às
  cegas por leitura de código, nunca vistos rodando. Trate-os como rascunho
  a validar e ajustar contra a imagem real, não como produto final.
- **Comando de voz já existe e já é mais completo do que parece**: em
  `App.tsx`, `sendToGod()` (linha ~625) é chamado tanto pelo texto digitado
  quanto pela transcrição de voz (`onTranscript` em `App.tsx` linha ~120
  chama `submitVoiceRef.current(text)`, que cai no mesmo `sendToGod`). Dentro
  de `sendToGod`, `inferRequestedPanel(normalized)` (em `appLogic.ts`) já
  abre painel por intenção de texto/voz (ex.: dizer "mostrar oportunidades"
  já abre o painel de oportunidades, por voz ou texto, hoje). Isso nunca foi
  testado com microfone real. **Não recrie esse mecanismo — verifique se
  funciona e estenda o vocabulário dele.**
- `frontend/src/voice.ts` faz reconhecimento de voz via Web Speech API do
  navegador (não há endpoint de transcrição no backend) e síntese de
  resposta via ElevenLabs (`backend/app/services/voice.py`, já real e
  testado).

## Parte 1 — Dashboard fiel à imagem (pixel-a-pixel, não aproximado)

Elementos que a imagem mostra e que precisam bater exatamente (posição,
proporção, texto, cor — ajuste `SystemPulseHeader.tsx`,
`UniverseConstellationLabels.tsx`, `ChronicleTicker.tsx` e o CSS em
`living-dashboard.css` até bater):

1. **Cabeçalho**: logo "THE CREATION OS" + "LIVING CORE" à esquerda; centro
   "PULSO DO SISTEMA" com onda tipo eletrocardiograma animada + círculo de
   percentual (ex. "98%") + rótulo de status ("ESTÁVEL"); direita "CRIADOR"
   + "ACESSO TOTAL" + ícone de pessoa. O percentual e o status **têm que
   vir de `/api/v1/pulse` de verdade** (`computePulseScore` já existe em
   `SystemPulseHeader.tsx` — audite se a lógica de pontuação está
   correta, teste derrubando Redis e confirme que o número cai e o rótulo
   muda).
2. **Núcleo central**: DEUS visualmente pequeno/quase invisível
   (`LivingUniverseScene` já trata isso via opacidade baixa — confirme
   visualmente).
3. **SOPHIA** (rótulo "SOPHIA" / "SABEDORIA" / "Compreende o contexto")
   orbitando à esquerda do núcleo; **ROCKMAM** ("ROCKMAM" / "POSSIBILIDADE"
   / "Avalia o que pode ser") orbitando à direita. Na imagem aparecem
   contagens ("12 AGENTES", "16 AGENTES") — **não invente esse número**:
   SOPHIA e ROCKMAM não têm agentes próprios no modelo de dados real. Ou
   substitua por uma métrica real e honesta (ex.: nº de compreensões/
   avaliações processadas na sessão), ou omita esse número para essas duas
   entidades — decida e documente a escolha, não fabrique.
4. **Cards de Universo** ao redor (a imagem mostra 5: Conhecimento,
   Segurança, Comunidade, Evolução, Infraestrutura — cada um com ícone,
   nome, descrição curta e contagem de agentes). O sistema real hoje só tem
   3 Universos **ativos** (`knowledge`, `engineering`, `security` — ver
   migration `0023_universe_agent_seed`), não 5, e não existe Universo
   chamado "Infraestrutura" no seed real. **Não force os 5 nomes da
   imagem se não existirem no backend.** Mostre os Universos ativos reais
   com contagem real de agentes (`agents.filter(a => a.enabled &&
   a.universe === code)`), no mesmo estilo visual da imagem, e resuma os 9
   inativos numa faixa discreta — isso já é a decisão tomada em
   `UniverseConstellationLabels.tsx`, só falta validar visualmente que fica
   parecido com a imagem apesar do número diferente de cards.
5. **Rodapé "CRÔNICAS DO SISTEMA"**: ticker horizontal com eventos reais
   recentes (`GET /api/v1/chronicles`), ícone/hora + frase curta, link "VER
   HISTÓRICO COMPLETO →" abrindo o painel completo já existente
   (`ChronicleRibbon.tsx`, no `demandPanel`). Frases devem ser reais
   (mapeadas de `event_type`, já implementado em `ChronicleTicker.tsx`
   `EVENT_LABEL` — audite se cobre os `event_type` que o backend realmente
   emite; se faltar algum, complete o mapa, não deixe cair no fallback
   genérico).
6. **Caixa de conversa**: "Fale com DEUS..." (rótulo mantido em português,
   não trocar para "GOD" — decisão já tomada e revertida uma vez nesta
   sessão) com botão de enviar e microfone.

Depois de ajustar, tire screenshot real (`http://127.0.0.1:5173`) e compare
lado a lado com a imagem que o Criador colou. Não declare "igual à imagem"
sem essa comparação visual de verdade.

## Parte 2 — Comando de voz em todos os elementos

O mecanismo de base (voz → texto → `sendToGod` → `inferRequestedPanel` →
`setRequestedPanel`) já existe. O trabalho aqui é **verificar com microfone
real** e **estender a cobertura**:

1. Teste com microfone real: falar "DEUS, mostre as oportunidades", "abrir
   o universo de engenharia", "mostrar auditoria" — confirme que o painel
   certo abre. Se não abrir, o defeito está em `inferRequestedPanel`
   (`appLogic.ts`) ou na captura de voz (`voice.ts`) — não invente um
   sistema de comando novo, conserte o existente.
2. Estenda `inferRequestedPanel`/`shouldClosePanel` (ou crie uma função
   irmã, mesmo padrão, mesmo arquivo) para cobrir ações que hoje só têm
   botão, sem equivalente de voz:
   - aprovar/rejeitar Inception (`api.approveInception`/`rejectInception`
     já existem, só faltam o reconhecimento de frase e o disparo);
   - aprovar/rejeitar Oportunidade;
   - abrir cada card de Universo individualmente por nome falado (hoje o
     clique em `UniverseConstellationLabels` abre o painel geral de
     "universes" — considere abrir com o Universo já focado/filtrado);
   - abrir o histórico completo de Crônicas ("mostrar todas as crônicas");
   - fechar qualquer painel aberto (`shouldClosePanel` já existe, confirme
     cobertura).
3. Todo comando de voz reconhecido como ação (não só navegação) precisa
   pedir confirmação do Criador antes de executar ação real (aprovar/
   rejeitar/autorizar) — **nunca execute uma decisão constitucional
   (aprovação de Inception, autorização de missão) direto de um comando de
   voz sem confirmação explícita**, isso violaria a Regra do Inception
   (só o Criador aprova, e precisa ser inequívoco). Implemente como
   confirmação de duas etapas: DEUS repete a intenção e pergunta
   "confirma?", só executa na resposta afirmativa seguinte.
4. Se, depois de tudo isso, o Criador ainda quiser transcrição no backend
   (em vez de só Web Speech API do navegador), implemente
   `POST /api/v1/voice/transcribe` em `backend/app/api/voice.py` +
   `services/voice.py`, seguindo exatamente o mesmo padrão de
   `VoiceSynthesisService` (auditoria via Chronicle, erros tipados,
   `require_creator`), usando o mesmo provedor já configurado
   (verifique se a conta ElevenLabs também oferece STT, ou se precisa de
   `EMBEDDING_PROVIDER`/outro provider — documente a escolha em
   `docs/architecture.md`). Trate isso como incremento opcional depois que
   o comando de voz via navegador estiver comprovadamente funcionando —
   não é bloqueante.

## Parte 3 — Fechar as lacunas funcionais reais (do relatório de comparação)

Ordem de prioridade — feche cada item com prova real de execução antes do
próximo, registrando em `docs/AUDIT_v0.5.md` (nova seção) como já é praxe
neste projeto:

1. **P4/P5** (`docs/AUDIT_v0.5.md`, punch-list): teste de integração real
   com dois workers concorrentes disputando o mesmo lease expirado
   (prova de reclaim sem dupla execução), e retry/backoff provado com o
   processo real do worker (falha → retry → sucesso, ponta a ponta, não só
   no nível de serviço).
2. **SOPHIA pede informação adicional quando falta contexto** (Protocolo
   SOPHIA v1.0, seções 6.1(3), 9, critério de conformidade 16). Hoje
   `core/sophia.py` só classifica em 4 tipos fechados
   (`SophiaUnderstandingType`), nunca devolve uma pergunta. Adicione um
   caminho onde, quando a compreensão for insuficiente (ver seção 7 do
   protocolo: "Compreensão insuficiente"), o retorno ao Criador seja uma
   pergunta objetiva (uma das listadas na seção 9.1 do protocolo) em vez de
   uma classificação fechada — sem criar engine nova, dentro do mesmo
   `sophia.py`/`god.py`/migration `0014_sophia_understanding` (a seção 15
   do protocolo proíbe explicitamente engine nova ou camada paralela).
3. **Eventos de Chronicle para as fases de SOPHIA** (seção 14 do
   protocolo: RECEBENDO, COMPREENDENDO, BUSCANDO_CONTEXTO, DISCERNINDO,
   SINTETIZANDO, AGUARDANDO_DECISÃO, APRENDENDO). Não crie uma máquina de
   estados persistida nova — registre essas fases como eventos de
   Chronicle dentro do fluxo determinístico já existente (ex.:
   `sophia.discerning`, `sophia.synthesizing`), auditável, sem mudar a
   arquitetura.
4. **Laço de aprendizado** (protocolo, seções 4 e 8): hoje `core/memory.py`
   só armazena memória (get/set/search), sem realimentar compreensão futura
   de SOPHIA a partir de resultado observado de missão. Avalie o menor
   incremento real: ao fechar uma missão (`malkuth.manifested`), consolidar
   um resumo em Conscious Memory que SOPHIA possa buscar/usar em
   compreensões futuras do mesmo assunto — sem fabricar uma feature de "IA
   que aprende" maior do que isso.

## Regras não negociáveis (repetidas porque continuam valendo)

- Não altere a arquitetura congelada nem as regras imutáveis.
- Não crie engine, núcleo conceitual ou fluxo paralelo fora do já
  existente — todo incremento acima cabe dentro dos arquivos e padrões já
  estabelecidos.
- Não execute ação constitucional (aprovar Inception, autorizar missão)
  por comando de voz sem confirmação explícita de duas etapas.
- Não declare build, teste ou comparação visual aprovados sem executar de
  verdade. Não esconda falha. Não fabrique número (contagem de agentes,
  percentual de pulso, nome de Universo) que não venha da API real.
- Não commite, não crie tag, não dê push sem autorização explícita do
  Criador.

## Entrega obrigatória ao final

- Screenshot real da interface final ao lado da imagem do Criador, com
  divergências explicadas (o que ficou igual, o que foi ajustado por ser
  dado real diferente da imagem — ex.: 3 Universos ativos, não 5).
- Prova de comando de voz funcionando com microfone real (transcrição do
  teste, não só código).
- Resultado real de P4, P5, e dos três incrementos de SOPHIA (perguntas,
  eventos de fase, aprendizado), cada um com teste automatizado novo e
  saída de execução colada.
- Resultado da suíte completa (`pytest`, `ruff`, `npm run test`,
  `npm run build`, `docker compose up`) depois de tudo.
- Lista de pendências reais que restarem, se houver.
