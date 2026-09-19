# Semantic Cache Orchestrator

The Creation OS uses a context-aware response cache, not a bare vector lookup. The cache is an optimization boundary between cognitive request construction and provider inference; it never replaces Memory, RAG, authorization, live-state retrieval, or capability execution.

## Decision path

`request -> policy -> exact lookup -> semantic candidates -> context/version/auth gates -> HIT | MISS | BYPASS | REVALIDATE`

A reusable entry is bound to Creator scope, optional Universe scope, intent, context hash/version, knowledge and retrieval versions, generation profile, cache policy version, authorization fingerprint, tool-state class, embedding model/version, and freshness. Private entries never cross Creator scope.

Live state, financial-live state, authorization/security decisions, external writes, transactions, mission/task execution, and action-capable tool requests bypass semantic reuse. `DOCUMENT_QA` is eligible only when both a retrieval fingerprint and knowledge version are supplied.

## Storage and failure model

Redis provides exact-cache hot storage, metrics and single-flight locks. PostgreSQL + pgvector provides durable entries, vector retrieval and audit events. Cache faults fail open: provider inference continues when Redis, vector search, embedding generation or cache admission is unavailable.

The migration uses variable-dimension pgvector storage. A partial HNSW cosine index accelerates the common 1536-dimensional path; other embedding dimensions remain supported with exact cosine search.

## Rollout

`SEMANTIC_CACHE_MODE` supports `off`, `shadow`, `exact`, and `semantic`. Production starts in `shadow`; promotion to `exact` and then `semantic` should occur only after false-hit and disagreement quality gates pass. Thresholds are bootstrap configuration, not permanent universal constants.

## Invalidation

Entries support tag-based, Creator-scoped invalidation. Knowledge/document/memory policy changes should emit invalidation tags and/or change their version/fingerprint; version mismatch itself prevents reuse. TTL is a secondary freshness defense, not the primary invalidation mechanism.

## Observability

Redis counters expose requests, exact/semantic hits, misses, bypasses, revalidations, writes, invalidations, shadow matches/disagreements, and single-flight hits. PostgreSQL records durable cache write/invalidation audit events. `/api/v1/system/cache` exposes authenticated operational status without exposing cached content.

## Safety invariants

- cache failure cannot become Creation failure;
- no action or capability execution is replayed from response cache;
- no private cross-Creator semantic reuse;
- no hidden chain-of-thought is persisted;
- cached provider metadata is restricted to an allowlist and sanitized;
- sensitive or `NO_CACHE` requests fail closed to bypass;
- semantic similarity alone is never sufficient for reuse.
