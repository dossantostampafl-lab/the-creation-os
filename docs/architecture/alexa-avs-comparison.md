# Sistema de voz do Deus × Alexa (AVS Device SDK)

Comparação entre o pipeline de voz atual (`frontend/src/voice-session/`,
`backend/app/voice_session/`) e o SDK público da Amazon
[`alexa/avs-device-sdk`](https://github.com/alexa/avs-device-sdk)
(commit `84aabe9`, jan/2024 — a última versão publicada).

> O SDK especifica só o **lado do dispositivo** e o protocolo com a nuvem.
> O reconhecimento de fala, a interpretação e a voz sintetizada da Alexa
> rodam fechados na nuvem da Amazon e não são públicos.

## 1. Máquina de estados

| Alexa (`DialogUXState` + `AudioInputProcessor`) | Deus (`GatewayState`) |
|---|---|
| `IDLE` | `ARMED` |
| — (wake word local, ver §2) | `WAKE_DETECTED` |
| `LISTENING` / AIP `RECOGNIZING` | `LISTENING` |
| AIP `BUSY` (fim da captura, aguardando resposta) | `COMMITTING` |
| `THINKING` | `THINKING` |
| `SPEAKING` | `SPEAKING` |
| `FINISHED` → `IDLE` | volta para `LISTENING` |
| `EXPECTING` (via diretiva `ExpectSpeech`) | **não existe** |

Os estados já estão quase 1:1. As diferenças relevantes são o retorno a
`IDLE` e o `EXPECTING` (§3).

## 2. Palavra de ativação

| | Alexa | Deus |
|---|---|---|
| Onde detecta | **No aparelho** (keyword detector local). Nada sai do dispositivo antes da wake word. | **Na nuvem**: regex `\bdeus\b` sobre o transcript do STT (`backend/app/voice_session/session.py:18`). O cliente envia todo o áudio desde `ARMED`. |
| Pre-roll | 500 ms de áudio antes da wake word são enviados junto (`PREROLL_DURATION`, `AudioInputProcessor.cpp:260`). | Não se aplica — o áudio já está todo no STT. |
| Verificação | A nuvem recebe `wakeWordIndices` (início/fim em amostras) e **re-verifica** a wake word; se for falso positivo, descarta (`StopCapture`). | Uma única etapa (regex no texto). |
| Quem iniciou | `initiator`: `WAKEWORD`, `TAP`, `PRESS_AND_HOLD`. | Só wake word. |

**Impacto:** custo de STT contínuo enquanto o microfone está aberto e
privacidade (toda fala do ambiente vai para a nuvem). É a maior diferença
de arquitetura.

## 3. Fim da conversa e follow-up

* **Alexa:** após `SPEAKING` volta para `IDLE`. Se a resposta pede
  continuação, a nuvem manda a diretiva `ExpectSpeech { timeoutInMilliseconds }`:
  o microfone reabre sem wake word e, se o usuário não falar no prazo, o
  dispositivo envia `ExpectSpeechTimedOut` e volta a `IDLE`.
* **Deus:** depois da primeira wake word, `_awake` fica `true` até a sessão
  fechar (`session.py:124`; só é zerado no construtor). Todo turno seguinte é
  aceito sem wake word, sem prazo.

## 4. Interrupção (barge-in)

| | Alexa | Deus |
|---|---|---|
| Gatilho | Wake word durante a fala. | VAD por energia (RMS ≥ 0.085, `useDeusVoiceSession.ts:124`) — qualquer som alto. |
| Cancelamento | `dialogRequestId`: o `DirectiveProcessor` (ADSL) descarta toda diretiva com id antigo. | `turn_id`: o cliente ignora `text_delta`/`audio_chunk` de turnos antigos ou cancelados (`session.ts:65-66`). |
| Estado do TTS | `INTERRUPTED` distinto de `FINISHED`. | Não diferencia. |

O mecanismo de `turn_id` é equivalente ao `dialogRequestId` — está correto.
O gatilho por energia é mais sujeito a falso barge-in (tosse, porta,
eco residual do próprio TTS, apesar de `echoCancellation: true`).

## 5. Foco de áudio e sons de sistema

* **Alexa:** `FocusManager` com canais priorizados `Dialog` > `Communications`
  > `Alert` > `Content` > `Visual`, e um `InterruptModel` que decide quando
  abaixar (duck) ou pausar o canal de menor prioridade. Earcons de sistema
  (`WAKEWORD_NOTIFICATION`, fim de escuta) dão feedback imediato.
* **Deus:** um único canal de áudio (`player.ts`). Há um "acknowledgement"
  falado e cacheado (`acknowledgement.py`) no lugar do earcon.

Só importa se o Deus passar a tocar outros áudios (música, alarmes) ao
mesmo tempo que a conversa.

## 6. Fim de fala (endpointing)

* **Alexa:** perfis ASR — `CLOSE_TALK` (cliente decide o fim da fala),
  `NEAR_FIELD`/`FAR_FIELD` (nuvem decide e manda `StopCapture`).
* **Deus:** a nuvem (STT) decide o `committed`; equivale a `NEAR_FIELD`.
  O cliente sempre envia `commit: false`.

## O que vale adotar (em ordem de impacto)

1. **Wake word local no navegador/app** com pre-roll de 500 ms e
   re-verificação na nuvem (já existente). Só começa a enviar áudio depois
   da detecção. Opções: openWakeWord ou Porcupine (WASM). Maior ganho de
   custo e privacidade.
2. **Janela de follow-up tipo `ExpectSpeech`**: depois de `SPEAKING`, ficar
   em `LISTENING` por N segundos (ex.: 8 s) e voltar para `ARMED` se ninguém
   falar; o backend pode estender quando a resposta termina em pergunta.
3. **Barge-in mais seletivo**: exigir a wake word ou fala contínua
   (> ~300 ms) em vez de um único frame acima do limiar.
4. **Earcon curto** em `WAKE_DETECTED` antes do acknowledgement falado,
   para feedback em < 100 ms.
5. *(Opcional)* `initiator` `TAP` — botão para falar sem wake word.

Itens 2–4 são pequenos e não mudam o protocolo do gateway; o item 1 muda
onde a detecção acontece e precisa de um evento novo (`wake` com índices
do áudio) no `protocol.ts`/`protocol.py`.
