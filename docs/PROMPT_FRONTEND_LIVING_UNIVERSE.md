# PROMPT — Verificação da Creator Interface (Living Universe)

Cole este prompt no Claude Code (ou outro agente com Docker, Node e shell
reais na sua máquina), rodando na raiz do repositório `THE CREATION OS`.

---

## Contexto

O checklist de release já passou 100% nesta sessão (340/340 pytest,
frontend 15/15 + build, Docker 5/5 saudável — ver `docs/AUDIT_v0.5.md`
§13). Depois disso, o Criador mostrou uma imagem de referência da Creator
Interface que ele quer (cena cósmica: núcleo central, SOPHIA e ROCKMAM ao
redor, Universos como constelações rotuladas, barra de Pulso do Sistema no
topo, rodapé de Crônicas do Sistema, caixa de conversa). A imagem em si
rotula o núcleo central como "GOD", mas o Criador pediu explicitamente para
manter o rótulo do app como "DEUS" — não troque esse texto. Essa cena
já existiu no projeto — está preservada no commit `8d24505` ("restore
frozen living universe experience") — mas o refator grande desta sessão
(ainda não commitado) tinha substituído a apresentação visual por um
dashboard mais simples, mantendo só a lógica funcional (canvas
`LivingUniverseScene`, já ligado a dados reais de `agents`/`universes`/
`pulse`).

A decisão do Criador foi: **não reverter** o trabalho funcional. Em vez
disso, sem acesso a Docker/npm/rede no ambiente anterior, foram escritos às
cegas (sem `tsc`/`npm run build` rodando) três componentes novos que somam
a apresentação visual de volta sobre a base funcional existente:

- `frontend/src/components/SystemPulseHeader.tsx` — barra superior: logo,
  onda de pulso animada e placar de saúde (`computePulseScore`, derivado
  só de campos reais de `pulse`: `database`, `redis`, `redis_streams`,
  `chronicles_chain.valid`, `failed_tasks`, `error_count` — nenhum número
  fabricado), badge do Criador.
- `frontend/src/components/UniverseConstellationLabels.tsx` — cards
  persistentes para SOPHIA/ROCKMAM e para cada Universo **ativo** (nome,
  ícone, descrição, contagem real de agentes via
  `agents.filter(a => a.enabled && a.universe === code)`); os 9 Universos
  inativos aparecem resumidos numa faixa compacta separada, não como cards
  "ativos" falsos.
- `frontend/src/components/ChronicleTicker.tsx` — rodapé persistente com
  os eventos reais mais recentes de `chronicles` (já buscados em
  `App.tsx`), com um mapa de `event_type` → frase curta em português, e um
  botão que abre o painel completo já existente (`ChronicleRibbon.tsx`,
  não alterado).

Essas peças foram integradas em `frontend/src/components/LivingDashboard.tsx`
(que já continha `LivingUniverseScene`, o canvas procedural com DEUS/SOPHIA/
ROCKMAM/Universos/agentes desenhados a partir de dados reais — isso não é
novo, só ganhou a camada de rótulos legíveis por cima). O rótulo visível
permanece "DEUS" (foi cogitado trocar para "GOD" para bater literalmente
com a imagem do Criador, mas ele pediu explicitamente para manter "DEUS" —
não altere esse texto). CSS novo
foi anexado a `frontend/src/styles/living-dashboard.css`, e os elementos
existentes (`conversation-dock`, `creator-access`, `transient-response`,
`system-state-binding`) foram reposicionados para não sobrepor o novo
rodapé de crônicas.

`App.tsx` foi atualizado para passar duas props novas ao `LivingDashboard`:
`chronicles={chronicles}` e `onSelectPanel={setRequestedPanel}`.

## O que já foi verificado sem Docker/npm

- Balanceamento de chaves/parênteses nos 4 arquivos tocados (não é
  substituto de compilar).
- Compatibilidade de tipos lida manualmente: `RequestedPanel` (em
  `appLogic.ts`) já inclui `"universes"` e `"chronicle"`, então
  `setRequestedPanel` é atribuível a `onSelectPanel`.
- Nenhum import órfão de componente antigo deletado (`GodCore`,
  `SophiaNode`, etc. — não foram restaurados, ficaram fora do escopo por
  decisão do Criador).

Nada disso substitui compilar e olhar a tela de verdade.

## O que fazer, em ordem

1. `git status --short` — confirme os arquivos esperados: os três
   componentes novos, `LivingDashboard.tsx`, `App.tsx` e
   `living-dashboard.css` modificados. Nada mais deveria ter mudado desde
   o último estado reportado em `docs/AUDIT_v0.5.md` §13.
2. `cd frontend && npm run test && npm run build` — se `tsc --noEmit` ou
   `vite build` apontar erro de tipo, o mais provável está em:
   - `LivingDashboardProps` (campos novos `chronicles` e `onSelectPanel`);
   - a chamada `<LivingDashboard ... />` em `App.tsx` (precisa passar
     `chronicles={chronicles}` e `onSelectPanel={setRequestedPanel}`);
   - os ícones SVG em `UniverseConstellationLabels.tsx` (spread de props
     comuns em `<svg {...common}>`).
   Corrija seguindo o mesmo padrão de investigação de
   `docs/AUDIT_v0.5.md` (reproduza antes de supor causa).
3. Suba o stack: `docker compose up -d --force-recreate` (ou
   `npm run dev` em `frontend/` apontando para a API já rodando, se mais
   rápido para iterar).
4. **Abra `http://127.0.0.1:5173` de verdade e compare com a imagem que o
   Criador mostrou.** Pontos específicos a checar:
   - o rodapé de Crônicas (`.chronicle-ticker`) não deve sobrepor a caixa
     de conversa (`.conversation-dock`) nem o formulário de login
     (`.creator-access`) — ambos foram levantados para `bottom: 108px`
     (96px no breakpoint mobile) para abrir espaço para o rodapé de 76px;
   - os cards de Universo (`UniverseConstellationLabels`) devem mostrar
     contagens de agentes reais, não zeradas ou erradas — confira contra
     `GET /api/v1/agents`;
   - o placar de pulso deve refletir de verdade o estado do stack (pare o
     Redis e confira se o percentual cai e o rótulo muda para
     "DEGRADADO"/"CRÍTICO");
   - responsividade abaixo de 900px e 760px (breakpoints já ajustados,
     mas não testados visualmente);
   - a faixa de "N universos inativos" não deve ser confundida com
     Universos ativos.
5. Tire um screenshot (ou descreva com precisão) do resultado atual lado a
   lado com a imagem de referência do Criador, e liste divergências reais.
6. Não corrija divergências de estilo por conta própria além de bugs
   óbvios (sobreposição, quebra de layout, erro de tipo) — ajustes finos de
   posição/cor devem voltar para o Criador decidir, já que isso é gosto
   visual, não correção técnica.

## Regras não negociáveis

- Não altere a arquitetura congelada, as regras imutáveis, nem toque no
  backend nesta tarefa.
- Não restaure os componentes antigos deletados (`GodCore.tsx`,
  `SophiaNode.tsx`, `RockmamNode.tsx`, `UniverseGalaxy.tsx`,
  `StarfieldCanvas.tsx`, etc.) — foi decisão explícita do Criador manter a
  base funcional atual (`LivingUniverseScene`) em vez de reverter para
  eles.
- Não declare build ou teste aprovado sem executar de verdade. Não
  esconda erro de tipo ou de layout.
- Não commite, não crie tag, não dê push sem autorização explícita do
  Criador — mesmo que tudo compile e pareça certo visualmente.

## Entrega obrigatória ao final

- Resultado real de `npm run test` e `npm run build` (output colado).
- Confirmação de que a interface abre em `http://127.0.0.1:5173` sem
  sobreposição quebrada.
- Screenshot ou descrição fiel do resultado, com divergências reais frente
  à imagem do Criador.
- Lista de qualquer correção feita, com arquivo e motivo.
