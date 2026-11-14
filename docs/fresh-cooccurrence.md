# Literal co-occurrence study

Search requests can optionally supply `required_terms`, a list of one to four
additional distinct literals. The primary query and every additional term must
occur within the same extracted record. For example, query `Invented` plus
required terms `["beta", "detail"]` finds a synthetic record containing all three.
The optional field is omitted for prior behavior; explicit JSON null is refused.
Terms are case-sensitive Unicode substrings, not tokenized, translated, stemmed
or normalized. Each is bounded to 128 code points with the same control-character
restrictions as the primary query. Duplicate terms and a repeated primary query
are refused. Substring terms may overlap: this does not imply distinct concepts.

Layer/review filtering and conjunction happen before pagination. Each additional
term has a separate labelled `required_term_locations` group, using the existing
32-location cap per returned record, with `more_locations` if truncated. Match
counts count extracted records, not distinct verses, quotations or occurrences.
The original primary-query `match_locations` remains unchanged.

Co-occurrence does not establish a semantic relationship, doctrinal agreement,
source endorsement or entailment. Records can overlap and contain quotations,
notes and nested material. Always inspect individual fragment provenance. No
source part, attribution, rights or admission flag is changed. Explicit private
study and disclosure permissions remain required; noncandidate text still needs
separate review permission. This is not a model or a training-data admission path.

The unchanged snapshot guard can refuse when unrelated ancestor directories
change. Earlier concurrent failures and unresolved private-source failures remain
open; this feature adds no retry or relaxation. Browser and real-corpus validation
are not performed here. Tests use invented fixtures only.

Validation: eight focused synthetic tests passed. An independent non-concurrent
full suite passed 960 tests in 70.612 seconds, with 54 optional skips. Independent
scope review found no gate bypass. An initial shell launch from the wrong working
directory could not open its log destination and executed no tests; it is not
counted as a pass. No retry or snapshot guard change was introduced.
