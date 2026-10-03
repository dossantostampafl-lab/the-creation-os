# Projeto DEUS: memória conectada e diagnóstico do Creation OS

**Status: projeto documental para auditoria. Nenhuma implementação foi aplicada.**

Data:2026-10-02. Base analisada:50924e3ca5b6f71a6a8287e2b19929da56306819. Diretório separado: /workspace/deus-memory-project. O repositório e a produção permanecem intactos.

## Resultado desejado

DEUS compreende o contexto acumulado do OS, inclusive em conversa nova e por voz. Conversas, decisões, resultados, documentos e diagnósticos chegam a uma memória central diretamente. Universos são especialidades e classificações, sem criar barreiras obrigatórias de informação.

## Ordem de leitura

1. [Brainstorm e decisões](BRAINSTORM.md): alternativas, escolhas e exclusões.
2. [Arquitetura geral](specs/00-arquitetura.md): fluxo, limites e contratos.
3. [Memória e ingestão](specs/01-memoria.md).
4. [Contexto de texto e voz](specs/02-contexto.md).
5. [Diagnóstico independente](specs/03-diagnostico.md).
6. [Exportação Obsidian](specs/04-obsidian.md).
7. [Auditoria](audit/01-matriz.md): pode, condicionado e adiado.
8. [Planos executáveis](plans/00-roteiro.md): tarefas, arquivos, interfaces e testes.
9. [Testes de aceitação](audit/02-aceitacao.md) e fixtures/: exemplos sintéticos.
10. [Parecer independente](audit/03-revisao.md), quando finalizado.

As interfaces e arquivos novos são propostas de implementação; não existem ainda no OS. Os planos usam caminhos relativos ao repositório de referência. Nenhum comando nos planos foi executado para alterar produto ou produção.

## Aprovação por etapas

Auditar e aprovar memória/contexto primeiro; diagnóstico e Obsidian têm planos independentes. Aprovar o documento não aprova deploy, negociação, execução de shell, instalação de todos os MCPs ou edição bidirecional. Execução futura deve ocorrer em branch/worktree própria com PRs pequenos e CI.

## Entrega e reversão

M1: DEUS recupera decisões entre conversas, igualmente em texto e voz. M2: diagnóstico contínuo com evidências. M3: Markdown navegável com links. Embeddings locais e sincronização bidirecional são extensões condicionais posteriores. Flags separadas permitem desativar recuperação/exportação sem apagar originais.
