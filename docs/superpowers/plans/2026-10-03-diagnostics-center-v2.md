# Centro de Diagnóstico v2 — implementation plan

**Spec:** docs/superpowers/specs/2026-10-03-diagnostics-center-v2-design.md

## Task 1 — estado ternário e sondas internas
- Estender `DiagnosticRules.observe` para `bool | None`.
- Adicionar sondas de projeções, tarefas paradas, Universos, journal e superfícies unknown de inferência/voz.
- Adicionar thresholds configuráveis.
- Testar unknown, lag, task stall, canon e spool-full.

## Task 2 — proveniência tipada
- Adicionar `diagnostic_observation` e `diagnostic_incident` ao contrato de conhecimento.
- Calcular hash determinístico para essas fontes.
- Publicar projeções de diagnóstico com source_id do registro local.
- Localizar revisão anterior pelo item canônico, não pelo source_id.
- Testar replay, substituição e source_type.

## Task 3 — verificação integral
- Rodar testes focados.
- Rodar suíte backend completa.
- Rodar Ruff e mypy.
- Validar CI do PR e revisar o diff inteiro.
- Integrar somente com todos os gates verdes.

## Review focus
- `unknown` não pode mascarar falha nem fabricar recuperação.
- Sondas devem ser somente-leitura.
- Limites de lag/stall devem ser configuráveis.
- Proveniência tipada não pode tornar evidência inválida ou quebrar revogação.
- Nenhuma dependência do Cyber Range.
