# Private source-study CLI

This separate, opt-in, read-only path does not add source records to canonical
reasoning, memory, a model provider, a robot or business decisions. The package
contains no source corpus or trained model. Private inputs and outputs belong
outside this checkout, package data, web assets and build context.

## Source and rights

Only the exact approved SARIT Sarvarthasiddhi XML and exact reviewed preparation
are accepted. This is one Digambara commentary on the Tattvarthasutra, not the
complete Agama canon. It is Latin-transliterated Sanskrit with quotation/editorial
language qualifications. No modern Hindi translation is included. This command
does not supply Hindi/Gujarati semantic question answering or translation.

The source's CC BY-SA 4.0 International attribution, editorial change notices and
exclusions accompany every response. Original scholarly_verified,
runtime_admitted and training_admitted flags remain false. A digest proves byte
identity, not scholarly accuracy or an absolute chain-of-title guarantee; the
source attribution retains the unknown-third-party-rights qualification.

Reuse must preserve applicable attribution/change notices and ShareAlike for
shared adaptations. Private access does not remove recipients' licence rights.
The software's MIT licence does not relicense source content or create a blanket
licence for trained weights. The command uploads nothing.

## Behavior

Literal lookup and paginated browsing preserve all 1,396 records with root/commentary/note categories,
citations, exact parsed text parts and warnings. Default lexical/fixed-blend
search uses 1,251 complete-citation root/commentary records without unresolved
quotation context. Incomplete IDs and notes remain literal-inspection-only,
through explicit lookup or browsing with the same per-invocation opt-in. No
missing citation, speaker or doctrinal endorsement is inferred.

Search is mechanical source-fragment matching, not semantic relevance or advice.
It requires an explicit sa-Latn language declaration and Latin-script fragments;
unsupported language/script or insufficient overlap causes abstention. These
guards are not comprehensive out-of-domain detection. Fixed ranking is
untrained. The separately reviewed experimental model is not loaded: its
code/protocol binding differs and must not be silently relabeled. Its accuracy
results do not qualify this CLI.

## Invocation

Use an authorized local POSIX Python 3.10+ environment with descriptor-relative
no-follow IO. Native Windows remains unsupported for this source path. No server,
browser, API token, provider or new credential is needed. There is no HTTP
source-study endpoint. The local OS controls file/process access; this is not a
multi-user authorization service.

Supply already prepared private files. The prepared directory must contain
records.jsonl, manifest.json, ATTRIBUTION.md and CHANGES.md from the exact
reviewed preparation. No download, copying, source discovery or persistent
consent occurs. Changed pinned bytes or notices require a separately reviewed
new version.

```sh
jace source-study --stdin \
  --source-file /absolute/private/source.xml \
  --prepared-dir /absolute/private/prepared-reviewed \
  --opt-in-source b2b767a893973aa92306ed9bd35566ee20368634e41db8efa5f2e1bb77250e9a \
  --opt-in-records e063a8c46cac36ad18777148f3e137ced8a7c3c7d24b533176697c522c041c1c \
  --accept-license CC-BY-SA-4.0 < /absolute/private/request.json
```

Lookup JSON: `{ "operation": "lookup", "id": "TAS_1.1" }`.
Browse JSON: `{ "operation": "browse", "limit": 5 }`. Browsing returns records
in the pinned preparation's order, without ranking. Optional `chapter` is an exact
string from `"1"` through `"10"`; optional `category` is `root_text`, `commentary`,
`editorial_note`, `paratext`, `quotation_fragment` or `edition_metadata`. Omit
unused filters rather than sending null. Filters select existing metadata only.
Unfiltered browsing includes records whose chapter is unassigned. Excluded notes,
quotations and incomplete citations remain marked; browsing does not make them
searchable or admitted. Adjacency is not a reviewed doctrinal relationship.

Each page reports `total` matching records and `next_offset`. To continue, repeat
the same filters with that `offset`, plus the same source/preparation/licence
opt-in on the new invocation. A null `next_offset` means the last page. Offsets
count records in the filtered preparation, starting at zero; changing filters
starts a different sequence, so restart at zero. Exact-end requests return an
empty `complete` response; offsets beyond the matching total are rejected.
The limit is 1-20, default 5. Requests and pages remain subject to the same byte
limits; if a page exceeds the output limit, retry explicitly with a smaller limit.
There is no persistent browsing session or automatic follow-up request.

Search JSON requires `operation: "search"`, `query`, and
`query_language: "sa-Latn"`, optionally integer `limit` (1-20) and `ranking`
(`lexical` or `fixed_blend`). Unknown fields, training, learned-model loading,
saving and action requests are rejected. Input is limited to 4 KiB; fully
validated output is bounded to 256 KiB. Queries come from stdin, not arguments.
Request files, shell history/redirects, terminals and other processes can still
retain input/output; the command does not manage those copies.

Every invocation opts into this source, preparation, purpose and licence. Paths
must be absolute without parent traversal or symlink components. Files must be
bounded regular files. Hash/Git-blob checks and verified-byte reuse protect source
identity. Session exit releases references, not a secure RAM wipe. No database
is opened; CognitiveEngine is never constructed, so configured model, canonical
and memory destinations are not used. The command writes no source, query,
result, credential or consent file; results go only to stdout.

## Packaging and future web boundary

Do not place private XML/JSON, weights or requests under src/jace/data: existing
package-data globs would include them. Keep them in an operator-controlled
directory, mounted read-only if containers are separately qualified. Docker's
explicit code/assets allowlist is not Docker runtime qualification. Repository
visibility and access are unchanged.

A future web mode needs approved runtime principals, authenticated source access,
source/dataset/licence/purpose/destination-bound consent, bounded owner-scoped
work, revocation and stale-response handling, no-store responses, no source in
public assets, an allowed browser route and qualified deployment. Repository
collaboration is not runtime authorization. These web controls are not implemented.

Synthetic tests cover consent, source integrity, no-follow IO, revocation, copied
outputs, flags/notes, complete ordered pagination, exact metadata filters,
exclusion/abstention, bounded JSON stdin, fixed-only ranking
and no-engine dispatch. Separate private smoke evidence checks approved local
source files without adding text to the repository or wheel. Browser/audio,
Windows, hosted access, multi-user service and doctrinal/business competence
remain unqualified.
