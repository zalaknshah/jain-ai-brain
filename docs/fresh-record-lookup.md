# Open pending items by preparation record ID

The request operation `lookup_record` takes `record_id` instead of `xml_id`, plus
exact pins/declaration and optional before/after context counts (0–8). It opens
one exact preparation record from the verified bundle. This completes the link
from pending-review queue entries even when their original XML ID is absent.

Confirmation and local disclosure permission remain required. A noncandidate
record or context window requires separate noncandidate-review permission. Exact
record equality, provenance, source notices and false admission flags are retained.
There is no fuzzy matching or fallback to another identifier, and IDs from another
preparation must not be reused without reselecting under the correct pins.

Preparation IDs are local extraction identifiers, not validated citations, verse
numbers, scholarly identity or stable identity across preparation revisions. The
result labels that distinction explicitly. Context is adjacent extracted records,
not inferred evidence or a guarantee of sufficient interpretive context. Missing
XML identifiers remain missing, and review status does not change.

The original XML-ID lookup remains available and unchanged. Mixed lookup/search
options are refused. Full source re-extraction, pin verification and snapshot
checks remain in effect, including known ancestor-directory availability refusals.
No guard change, retry, source upload, model invocation or training occurs.

Qualification here uses invented fixtures only, including a queue record lacking
an XML ID. Earlier private-source failures remain unresolved; no browser or
scholarly validation is implied.

Seven focused synthetic tests passed. Independent scope review found no gate or
identifier fallback issue; the independent sequential full suite passed 980 tests
in 70.065 seconds with 54 optional skips. This does not establish real-source or
concurrent reliability, scholarly review or model quality.
