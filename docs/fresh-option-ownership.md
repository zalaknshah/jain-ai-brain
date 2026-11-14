# Source-study option ownership

The direct Python API now owns bounded shallow snapshots of XML-ID selections and
additional literal terms before validation and bundle IO. The copied elements
must validate as immutable strings. The caller's original lists are never
modified. Each snapshot contains at most the allowed count plus one overflow element;
existing validation refuses overflow. No unbounded list copy is made.

Previously, changing a caller-owned list while a bundle was opening could alter
its later scope: clearing additional terms broadened a conjunctive search, and
changing selected IDs changed which records were disclosed or their order.
Four deterministic synthetic callback tests reproduced this against082f4f, all
four failed. The tests mutate caller lists during snapshot entry, without changing
bundle files or bypassing the existing file verification guard. They do not claim
to simulate an adversarial process with arbitrary Python execution privileges.

The fix preserves validated initial options through the invocation. It does not
add scholarly review, semantic authority or a new permission. Noncandidate gates,
source fingerprints, notices and immutable source handling remain unchanged.
Existing ancestor-mutation refusals and historical private-source failures remain
unresolved. There is no retry, browser run, real corpus test or model training.

An initial setup/test command could not start because its requested working
directory did not yet exist; no command or test executed. After creating the
isolated snapshot, the four expected baseline failures were captured separately.

Independent review found an oversized-list corner case in the initial fix: an
original list left caller-owned could shrink before validation then mutate later.
The final fix uses bounded slices unconditionally for exact lists, so every
accepted list is owned. The initial full suite passed 964 tests with 54 skips,
but applies only to the pre-correction version and is not final-code evidence.

Final-code validation: six focused tests passed. Independent review confirmed
all accepted lists are owned; the final sequential full suite passed 966 tests
in 69.707 seconds with 54 optional skips. This does not resolve unrelated source
snapshot availability failures or establish model/scholarly qualification.
