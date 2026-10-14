# Receiver safety contract v1.1 / v2.1

Implementation baseline: 389f7d0f8b335378c1cb61c511ef85735119a0db. These validation revisions retain the wire names shadow-display-v1 and local-display-v2. They do not change indicator/forecast formulas or data qualification.

## Approved validation revisions

- shadow-public-validation-v1.1: daily chart projection/typed validation and trend line preservation.
- shadow-receipt-validation-v1.1-v2.1: version-specific acknowledgement validation, independent of compression.
- local-display-validation-v2.1: validation at ingestion and every stored read, chart identity/type/date binding and bounded immutable publication.

## Compatibility and chart rules

Sparse legacy empty v1 charts and sparse v2 charts remain supported. Their map key supplies instrument identity and the enclosing manifest supplies the cutoff when those chart fields are absent. v1 populated bars retain required OHLC fields; v2 existing sparse bars may omit individual OHLC fields. Any supplied OHLC/indicator/level/trend numeric value must be finite, excluding booleans and nested objects.

Supplied ts_code must match the map key; v2 chart keys must belong to the manifest universe. Supplied as_of must be timezone-aware and no later than generated_at. Dates are exact daily ISO dates, strictly increasing/unique, and no later than the Shanghai date at the cutoff. Supplied source_as_of matches the final visible bar date when a series is nonempty; an empty historical/unavailable chart may retain its earlier source date. If both raw/research series are nonempty their date sequences agree.

Public chart/study safety flags, when supplied, remain research-only/UNKNOWN/non-actionable. Cost overlays remain false. Study and level fields have explicit scalar/list types; trend lines preserve exactly the eight public label/method/index/price/slope fields. Projection removes unknown fields; receiver validation rejects unknown chart/bar/study/level/trend fields.

## Delivery and gzip

Both wire contracts support gzip enabled/disabled. Bearer/HMAC/nonce handling is unchanged and authenticates wire bytes before parsing/decompression. The gzip reader requests at most max_decompressed_bytes + 1 output bytes, rejecting overflow before JSON parsing. Settings explicitly define decompressed and committed-generation budgets (default 64 MiB, configuration cannot raise them above 64 MiB).

Only HTTP 200 can acknowledge delivery. Receipts are objects with unique JSON keys and at most 4096 bytes.

| Wire contract | Required and allowed receipt keys |
|---|---|
| shadow-display-v1 | bundle_id |
| local-display-v2 | bundle_id, manifest_hash, status, sequence, received_at |

bundle_id equals the digest of the uncompressed manifest. For v2, manifest_hash agrees with that digest; sequence is the exact positive manifest sequence, not a bool; status is accepted or already_accepted; received_at is a timezone-aware ISO timestamp. Missing, extra, malformed or mismatched receipt data never records upload success.

## Stored reads, IDs and budgets

Every v2 read verifies the manifest-derived file identity, sequence/filename, parts hashes, chart rules, private-field safety and non-actionability across the entire envelope. A damaged pointer/cache produces unavailable data; safety flags are never silently repaired or masked into a valid result.

A full 64-hex string is always a bundle ID and must match exactly, including an all-numeric hash. A numeric short string is resolved against both sequence and hash-prefix aliases and rejected if they select different valid generations; an explicit integer selects the sequence namespace. Existing numeric sequence and 16–63-hex prefix aliases remain supported only when exactly one valid generation matches. No requested ID falls back to latest. Short source code_sha (7–40 hex) remains supported.

Budget covers committed hash-named generation JSON bytes; fixed bounded pointer/lock metadata and filesystem overhead are separate. Unknown user files are never garbage-collected. A prospective publication is validated and space/retention planned before mutation. Current latest becomes previous and is protected with the new generation. If that protected pair cannot fit, publication rejects with all existing files and pointers unchanged. Successful publication may prune other generations, retaining at most five. Existing over-budget state rejects further publication rather than silently deleting protected data. Small synthetic limits test these properties without allocating large files.

Publication locks do not reclaim an existing lock merely because its age exceeds two hours. A failed acquirer cannot unlink an owner's lock. Same-generation simultaneous deliveries serialize and return one accepted receipt plus already_accepted receipts with the same ID. Same sequence/different identity is rejected even if a file already exists. Filesystem errors attempt to restore prior files/pointers; unrecoverable OS/disk failures still require operator recovery.

## Policies deliberately retained or deferred

- No default expiry-policy change: publish still applies expiry only when its caller supplies now; historical STALE reads remain possible. Whether an expired package may activate is a separate pending decision.
- No forced expansion of source SHA to 40 characters.
- Private-account pricing generation, remaining endpoint migration, cloud job retirement, production switch, provider permission/license/PIT/OOS and real deployment acceptance remain outside this stage.
- No strategy qualification/calibration promotion, automatic trading, installation, push or deployment.
- A publication lock left by a crashed process requires explicit recovery; this stage favors unavailable delivery over stealing a potentially active lock.

