"""Versioned scoped knowledge, durable event receipts and DEUS context traces."""
from alembic import op

revision = "0012_deus_knowledge"
down_revision = "0011_stf_runtime"
branch_labels = None
depends_on = None

def upgrade():
    op.execute('\nCREATE TABLE knowledge_epochs (\n\tcreator_id VARCHAR(36) NOT NULL, \n\tversion BIGINT NOT NULL, \n\tPRIMARY KEY (creator_id), \n\tFOREIGN KEY(creator_id) REFERENCES creator (id) ON DELETE CASCADE\n)\n\n')
    op.execute('\nCREATE TABLE knowledge_projects (\n\tid VARCHAR(36) NOT NULL, \n\tcreator_id VARCHAR(36) NOT NULL, \n\ttitle VARCHAR(200) NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (id, creator_id), \n\tFOREIGN KEY(creator_id) REFERENCES creator (id) ON DELETE CASCADE\n)\n\n')
    op.execute('\nCREATE TABLE deus_context_traces (\n\tid VARCHAR(36) NOT NULL, \n\tcreator_id VARCHAR(36) NOT NULL, \n\tconversation_id VARCHAR(36) NOT NULL, \n\tdata JSON NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(creator_id) REFERENCES creator (id) ON DELETE CASCADE, \n\tFOREIGN KEY(conversation_id) REFERENCES conversations (id) ON DELETE CASCADE\n)\n\n')
    op.execute('\nCREATE TABLE deus_conversation_turns (\n\tid VARCHAR(36) NOT NULL, \n\tconversation_id VARCHAR(36) NOT NULL, \n\trequest_id VARCHAR(36) NOT NULL, \n\tcontent_hash VARCHAR(64) NOT NULL, \n\towner VARCHAR(36) NOT NULL, \n\tstate VARCHAR(16) NOT NULL, \n\tlease_until TIMESTAMP WITH TIME ZONE NOT NULL, \n\tresponse JSON, \n\tPRIMARY KEY (id), \n\tUNIQUE (conversation_id, request_id), \n\tFOREIGN KEY(conversation_id) REFERENCES conversations (id) ON DELETE CASCADE\n)\n\n')
    op.execute('\nCREATE TABLE knowledge_items (\n\tid VARCHAR(36) NOT NULL, \n\tcreator_id VARCHAR(36) NOT NULL, \n\tproject_id VARCHAR(36), \n\tcurrent_revision_id VARCHAR(36) NOT NULL, \n\tactive BOOLEAN NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (id, creator_id), \n\tFOREIGN KEY(project_id, creator_id) REFERENCES knowledge_projects (id, creator_id), \n\tFOREIGN KEY(creator_id) REFERENCES creator (id) ON DELETE CASCADE\n)\n\n')
    op.execute('\nCREATE TABLE knowledge_relations (\n\tid VARCHAR(36) NOT NULL, \n\tcreator_id VARCHAR(36) NOT NULL, \n\tfrom_id VARCHAR(36) NOT NULL, \n\tto_id VARCHAR(36) NOT NULL, \n\tkind VARCHAR(32) NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(from_id, creator_id) REFERENCES knowledge_items (id, creator_id) ON DELETE CASCADE, \n\tFOREIGN KEY(to_id, creator_id) REFERENCES knowledge_items (id, creator_id) ON DELETE CASCADE, \n\tUNIQUE (from_id, to_id, kind)\n)\n\n')
    op.execute("\nCREATE TABLE knowledge_revisions (\n\tid VARCHAR(36) NOT NULL, \n\tcreator_id VARCHAR(36) NOT NULL, \n\titem_id VARCHAR(36) NOT NULL, \n\tordinal INTEGER NOT NULL, \n\ttitle VARCHAR(200) NOT NULL, \n\tcontent TEXT NOT NULL, \n\tkind VARCHAR(32) NOT NULL, \n\tepistemic_state VARCHAR(16) NOT NULL, \n\tlifecycle VARCHAR(16) NOT NULL, \n\tsource_type VARCHAR(32) NOT NULL, \n\tsource_id VARCHAR(36), \n\tsource_hash VARCHAR(64), \n\tcontent_hash VARCHAR(64) NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tvalid_until TIMESTAMP WITH TIME ZONE, \n\tsearch_vector TSVECTOR GENERATED ALWAYS AS (to_tsvector('portuguese'::regconfig, title || ' ' || content)) STORED NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (id, creator_id), \n\tUNIQUE (item_id, ordinal), \n\tFOREIGN KEY(item_id, creator_id) REFERENCES knowledge_items (id, creator_id) ON DELETE CASCADE\n)\n\n")
    op.execute('\nCREATE TABLE knowledge_dependencies (\n\trevision_id VARCHAR(36) NOT NULL, \n\tsource_revision_id VARCHAR(36) NOT NULL, \n\tcreator_id VARCHAR(36) NOT NULL, \n\tPRIMARY KEY (revision_id, source_revision_id), \n\tFOREIGN KEY(revision_id, creator_id) REFERENCES knowledge_revisions (id, creator_id) ON DELETE CASCADE, \n\tFOREIGN KEY(source_revision_id, creator_id) REFERENCES knowledge_revisions (id, creator_id) ON DELETE CASCADE\n)\n\n')
    op.execute('\nCREATE TABLE knowledge_outbox (\n\tsequence BIGSERIAL NOT NULL, \n\tcreator_id VARCHAR(36) NOT NULL, \n\trequest_key VARCHAR(200) NOT NULL, \n\tpayload_hash VARCHAR(64) NOT NULL, \n\titem_id VARCHAR(36) NOT NULL, \n\trevision_id VARCHAR(36) NOT NULL, \n\tPRIMARY KEY (sequence), \n\tUNIQUE (creator_id, request_key), \n\tFOREIGN KEY(creator_id) REFERENCES creator (id) ON DELETE CASCADE, \n\tFOREIGN KEY(item_id) REFERENCES knowledge_items (id) ON DELETE CASCADE, \n\tFOREIGN KEY(revision_id) REFERENCES knowledge_revisions (id) ON DELETE CASCADE\n)\n\n')
    op.execute('\nCREATE TABLE knowledge_receipts (\n\tconsumer VARCHAR(64) NOT NULL, \n\tsequence BIGINT NOT NULL, \n\tprocessed_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (consumer, sequence), \n\tFOREIGN KEY(sequence) REFERENCES knowledge_outbox (sequence) ON DELETE CASCADE\n)\n\n')
    op.execute('CREATE INDEX ix_knowledge_projects_creator_id ON knowledge_projects (creator_id)')
    op.execute('CREATE INDEX ix_deus_context_traces_creator_id ON deus_context_traces (creator_id)')
    op.execute('CREATE INDEX ix_knowledge_items_creator_id ON knowledge_items (creator_id)')
    op.execute('CREATE INDEX ix_knowledge_revisions_creator_id ON knowledge_revisions (creator_id)')
    op.execute('CREATE INDEX ix_knowledge_revisions_item_id ON knowledge_revisions (item_id)')
    op.execute('CREATE INDEX ix_knowledge_search ON knowledge_revisions USING gin (search_vector)')
    op.execute("CREATE FUNCTION knowledge_revision_immutable() RETURNS trigger AS $$ BEGIN RAISE EXCEPTION 'knowledge revisions are immutable'; END; $$ LANGUAGE plpgsql")
    op.execute("CREATE TRIGGER knowledge_revision_no_update BEFORE UPDATE ON knowledge_revisions FOR EACH ROW EXECUTE FUNCTION knowledge_revision_immutable()")

def downgrade():
    op.execute('DROP TABLE knowledge_receipts')
    op.execute('DROP TABLE knowledge_outbox')
    op.execute('DROP TABLE knowledge_dependencies')
    op.execute('DROP TABLE knowledge_revisions')
    op.execute('DROP TABLE knowledge_relations')
    op.execute('DROP TABLE knowledge_items')
    op.execute('DROP TABLE deus_conversation_turns')
    op.execute('DROP TABLE deus_context_traces')
    op.execute('DROP TABLE knowledge_projects')
    op.execute('DROP TABLE knowledge_epochs')
    op.execute("DROP FUNCTION knowledge_revision_immutable()")
