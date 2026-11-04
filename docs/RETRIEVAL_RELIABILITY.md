# Bounded lexical retrieval and regression evidence

JACE's retrieval is lexical and associative, not semantic search or learned reasoning. This change fixes two concrete losses: directly matching memories older than the latest 100 active rows were ignored, and graph results could replace the direct ranking with newest-first rows. The local reasoner's fixed suggestions still do not interpret or reconcile personal memories.

## Selection behavior

- Direct memory search streams the selected owner's exact memory scope, scoring distinct normalized lexical term overlap. It retains only the requested top-k candidates. Equal scores prefer the newer memory ID, as before. Old rows are now eligible within the work budgets below.
- Direct matches remain first in engine context. Graph associations supplement unused slots in graph rank order, never replacing a direct match. At most five memories reach the reasoner.
- Graph IDs are rehydrated from the authoritative memory table with owner, exact scope and expiry checks. The same context timestamp applies to all retrieval stages. This is not revocation of an already-running request or protection against clock rollback.
- Graph traversal keeps the strongest path arriving at the same depth, independent of edge insertion or set iteration order. It still uses at most two hops and a lexical association heuristic, not a global optimum or semantic relevance proof.
- Only the active content-addressed corpus namespace participates in graph candidate scanning. Historical corpus versions remain stored but cannot supply active evidence or consume that candidate budget.
- Queries with no lexical terms retain the existing explicit recent-memory fallback. A numeric-only query can therefore return recent memories in the selected scope. It does not mean numeric search is supported.

## Work limits and failure behavior

These are application work limits, not process memory, CPU or absolute latency guarantees:

| Work | Bound |
| --- | --- |
| Query | 10,000 characters, 256 distinct normalized lexical terms |
| Result count for each retrieval call | 1–100; engine context remains five sources and five memories |
| Each candidate scan | 10,000 rows and 16 MiB of counted UTF-8 text |
| Each scanned text field | 32,768 characters |
| Graph expansion | Two hops; 50,000 fetched edge rows total, including repeated rows across SQL chunks |
| SQL frontier chunk | 400 node IDs, at most 800 parameters |
| Graph memory rehydration | At most 100 positive 64-bit IDs, with authorization and expiry rechecked |
| New or corrected memory content | 10,000 characters, checked before persistence |

Memory search holds O(k) ranked candidates rather than sorting all owned text. The graph retains its eligible candidate set within the row/text budgets. Canonical files are still loaded at startup; these query budgets do not bound corpus parsing, total database size, SQLite internals or every object allocation. Scanning is linear, not indexed semantic retrieval. A large number of expired rows also consumes the memory candidate budget. Existing oversized stored records can make retrieval fail until explicitly reviewed/corrected/deleted; this change does not truncate or delete them.

Exceeding a retrieval budget raises a controlled validation error, not an apparently complete partial context. In the HTTP think route this is a 400 response before model invocation or opt-in learning. Choose a narrower existing memory scope or review the dataset; merely rephrasing a query does not reduce all candidate scans. There is no silent fallback to the most recent 100 rows. No automatic memory relocation or cleanup occurs.

## Original synthetic evaluation

Run from the checkout, without model credentials or downloads:

```sh
python scripts/evaluate_retrieval.py
PYTHONPATH=src python -m unittest discover -s tests -p test_retrieval_reliability.py -v
```

The ten checked-in cases use original fictional equipment/location records and synthetic memories, including an original Hindi sentence. Their `verified` fields are fixture metadata, not a scholarly review or an assertion about sacred texts. Each case has a fresh temporary database, explicit relevant source/memory IDs, and at most 200 newer noise memories. The runner uses `LocalReasoner` explicitly and never sends a model request or opens the user's memory database.

The same fixtures were run against an untouched archive of baseline `7e49ce01e8a45c8bc21c2b868eeab252364b279c` and implementation `8d382da03cca0635c408fac07e679354c67f9a77`:

| Measurement | Baseline | Candidate |
| --- | ---: | ---: |
| Mean memory recall@5, six positive queries | 0.5833 | 1.0000 |
| Mean memory reciprocal first-relevant rank@5, six positive queries | 0.6667 | 1.0000 |
| Correct empty-label memory queries | 4/4 | 4/4 |
| Unlabeled memory returns across the ten cases | 0 | 0 |
| Mean source recall@5, five positive queries | 1.0000 | 1.0000 |
| Correct empty-label source queries | 5/5 | 5/5 |
| Full fixture assertions, including required first-memory ordering | 6/10 | 10/10 |

Recall is the fraction of labeled relevant IDs found within k. Reciprocal rank uses only the first relevant result. Required stronger-match ordering is a separate fixture assertion; reciprocal rank alone does not measure that distinction. Empty-label cases report an explicit empty-result check and are excluded from positive-query metric averages, not counted as perfect recall. Labels are exhaustive only for these deliberately small fictional fixtures. Unlabeled returns are diagnostics, not a universal relevance judgment.

This is a development regression set designed around observed failures, not a blinded holdout benchmark. These numbers do not establish real-user retrieval quality, translation, semantic relevance, correct source interpretation, model answer quality, safety, scholarly grounding or Agama coverage. Qualified human labels on a separately reviewed, legally usable corpus and representative held-out requests remain a delivery gate.
