# S4 — exportação Obsidian

Exportação unidirecional: banco canônico → Markdown. Não é clone do aplicativo Obsidian e não possui edição/sync bidirecional no MVP.

## Contrato e arquivos

ObsidianExporter.export(scope,root,cursor) -> ExportReport(written,removed,skipped,conflicts,cursor). ExportManifest mantém item_id/revision_id/hash do arquivo gerado. Caminho é root/<creator_uuid>/<kind>/<item_uuid>.md; título fica no frontmatter, nunca controla path. Evitar separadores/metacaracteres e seguir root permitido; recusar symlink/root compartilhado inadequado.

Frontmatter schema_version:1, id, revision_id, creator_id, kind, title, status, epistemic_state, source_type, source_id, occurred_at, exported_at. Corpo: conteúdo escapado/tratado como texto Markdown; relações como [[uuid|Título]]. YAML emitido com biblioteca segura, não concatenação de valores externos. Não colocar segredos, fontes fora do scope nem URLs autenticadas em notas.

## Consistência e conflitos

Export descobre eventos via receipts próprios conformeS1, sem perder commits fora de ordem; ExportReport.cursor é posição informativa do lote, não filtro exclusivo de seleção. Export de snapshot consistente e leitura revalidada; manifest escrito atomicamente via rename. Gravar temporário no mesmo filesystem, fsync/replace porarquivo. Se origem mudou antes de concluir, agendar nova revisão; não declarar exportado o que não corresponde ao manifest.

Só sobrescrever arquivo se hash atual igual ao manifest anterior. Se usuário editou localmente, registrar conflito e deixar arquivo intacto; escrever atualização em diretório de conflitos separado com IDs, sem ler nota editada como memória automaticamente. Não exportar notas com paths arbitrários oriundos de wikilinks.

Revogar/excluir origem remove arquivo somente se foi gerado pelo exporter e ainda corresponde ao hash. Em conflito, mover nota gerada/editada para quarentena privada com manifesto; ela deixa de estar no vault ativo. ExportReport indica arquivos não removidos por conflito/permissão e solicitação de limpeza manual. Não garantir remoção das cópias que usuário fez fora do diretório administrado.

## Requisitos operacionais

Volume export dedicado, permissões privadas, porCreator; máximo256KiB por nota conforme limite de fonte. Reexecução com mesmo cursor não duplica arquivos. Manifest inclui checkpoint, não usa nome/título para identidade. Exportação desligada não interrompe conversa. Download zip do vault é operação autenticada e explícita, fase posterior à geração local se necessária.

Sem monitorar edições, plugins de Obsidian, canvas ou publicar notas na internet nesta fase. Corpus importado de Obsidian precisaria parser/importer isolado e controle de conflitos específico.

## Journal de exportação e limpeza recuperável

ExportOperation(op_id,creator_id,item_id,revision_id,old_hash,new_hash,managed_paths,state prepared|applied|confirmed|cleanup_pending). Journal privado durável fsync registra prepared antes de substituir arquivo. Após substituir/confirmarhash, applied; manifest só avança ao estado confirmed. No crash entre arquivo e manifest, retry reconhece new_hash da operação preparada como escrita legítima, não edição do usuário; old_hash permite retomar operação não aplicada. Hash diverso de ambos gera conflito. Lock porCreator impede dois exports simultâneos; manifest é reconstruível via journal.

managed_paths inventaria nota principal, atualizações em conflitos, temporários e quarentenas gerados. Revogação agenda limpeza de todos arquivos administrados, inclusive cópia de atualização em conflitos; cópia editada pelo usuário pode ser preservada em quarentena privada fora do vault, com registro explícito de retenção. Falha de permissão mantém cleanup_pending durável e não avança a confirmação de limpeza. Operações pendentes são varridas em cada execução mesmo sem novos eventos; checkpoint/receipt não esquece revogação. Nenhuma cópia administrada sensível fica exposta no vault como atual após revogação concluída.
