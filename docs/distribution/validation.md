# Evidência de validação — 2026-10-03

Ambiente: Linux, PostgreSQL16/pgvector e Redis7 reais; banco descartável separado com guarda de segurança. Node24/JDK21/SDKAndroid36. Nenhum dado de produção foi usado nos testes locais.

| Verificação | Resultado observado |
|---|---|
| Suíte backend antes do último fechamento de contexto/ativação | 812passaram;1teste de fornecedor externo não executado. |
| Backend focal após packet/diagnóstico/foco | 64passaram; fechamento adicional de rollback/foco validado separadamente. |
| Rust gateway `cargo test --locked` | 20passaram, nenhum erro. |
| Ruff/mypy | Sem erros;188módulos verificados. |
| FrontendVitest | 37passaram. |
| PlaywrightChromium | 40passaram: cinco turnos contínuos, interrupção, autenticação, layouts, CSP/PWA. Entradas de voz simuladas; não substitui teste em aparelho. |
| CyberRangeDocker | Controller/JuiceShop/WebGoat/WebWolf responderam; verificadorloopback passou. Contratos/restauração/relay passam em testes. |
| AndroidGradle | `assembleDebug bundleRelease` passou; APKdebug e AABrelease produzidos. Sem assinatura de distribuição. |
| iOS | ProjetoXcode/SwiftPM, ícones/microfone/privacy preparados. BuildmacOS e dispositivo verificados separadamente pelo workflow; não pressuporIPA assinado. |

Últimasexecuções locais e CI da revisão devem prevalecer sobre esta tabela. Não há garantia de “zero bugs”, latência abaixo de um segundo, automação de negociação ou aprovação de loja. O corpus/limites e a autonomia pesquisando fontes internas estão descritos no runbookconectado.

Auditoria: corrigidos fenceapóscommit, escrita temporária por symlink, respostas sem dependência de evidência, diagnóstico sem projeção inicial, histórico não validado em timeout, foco cruzado e rollback parcial. Há testes de regressão para esses casos.
