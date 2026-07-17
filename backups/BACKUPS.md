# THE CREATION OS - SQL Backup Inventory

Generated: 2026-07-15

Validation method: SHA-256 hash, PostgreSQL plain dump header/footer, Alembic revision block, and COPY terminator count. No restore, migration, test, or database mutation was executed.

## Classification Summary

| Classification | Count | Notes |
| --- | ---: | --- |
| sovereign | 0 | No current canonical sovereign backup was present in the workspace. |
| recovery | 4 | Clean pre-migration recovery points. |
| contaminated | 3 | Explicitly marked contaminated by filename. |
| legacy | 1 | Older v0.3 backup retained for historical reference. |

## Backups

| File | Alembic revision | SHA-256 | Date | Classification | Status |
| --- | --- | --- | --- | --- | --- |
| `backups/contaminated/backup_contaminated_post_v045.sql` | `0008_agent_execution` | `fdf9417d8603ad38d65379a3bdd7ec6bace678eb9f50f055a403e1fc7945017a` | 2026-07-12 23:14:23 | contaminated | valid |
| `backups/contaminated/backup_contaminated_pre_restore_v0_4_4.sql` | `0007_agent_dispatcher_protocol` | `dcdd053323c0a28defec63f328bdb14e85c43e6c4fc8a74161aae6c83da93dd0` | 2026-07-12 20:47:57 | contaminated | valid |
| `backups/contaminated/backup_contaminated_pre_restore_v0_4_5_1.sql` | `0008_agent_execution` | `b9170ca30f48cd746bb4a46341d29e2b0b33f49f97139f42ecf6536e54bb686a` | 2026-07-13 21:08:31 | contaminated | valid |
| `backups/legacy/backup_v0_3.sql` | `0003_stabilization` | `813e8ded557c4e7a738044f58f4378936276ee3ddaa9f07bd0c7fd16b1751096` | 2026-07-12 12:16:59 | legacy | valid |
| `backups/recovery/backup_v0_4_1_pre_migration.sql` | `0003_stabilization` | `dd2181cf8bb18c643686a4b6c9e21ac8510a481f583a8645d385080e3115736e` | 2026-07-12 16:26:29 | recovery | valid |
| `backups/recovery/backup_v0_4_2_pre_migration.sql` | `0004_tree_core_foundation` | `f1b90c8061374cedc6edd3162aa67e13e551e04f4334b085e0602fe925b69654` | 2026-07-12 18:34:23 | recovery | valid |
| `backups/recovery/backup_v0_4_3_pre_migration.sql` | `0006_dispatch_queue` | `e54078e1bb73e0c7954929adc995c78a867dc2ddb2fd86249e2c36e9e52da73f` | 2026-07-12 19:47:13 | recovery | valid |
| `backups/recovery/backup_v0_4_5_pre_migration.sql` | `0007_agent_dispatcher_protocol` | `e295c791780622748c8f4172bfc9f94b062d60675f4262028724672bbbfe589d` | 2026-07-12 22:46:49 | recovery | valid |

## Final Folder Layout

```text
backups/
  BACKUPS.md
  contaminated/
    backup_contaminated_post_v045.sql
    backup_contaminated_pre_restore_v0_4_4.sql
    backup_contaminated_pre_restore_v0_4_5_1.sql
  legacy/
    backup_v0_3.sql
  recovery/
    backup_v0_4_1_pre_migration.sql
    backup_v0_4_2_pre_migration.sql
    backup_v0_4_3_pre_migration.sql
    backup_v0_4_5_pre_migration.sql
  sovereign/
```
