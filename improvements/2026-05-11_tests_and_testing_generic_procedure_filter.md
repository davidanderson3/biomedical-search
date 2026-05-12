# Tests And Testing Generic Procedure Filter

## Goal

Prevent the generic procedure concepts `tests and testing` and `Tests` from appearing as search results. These labels are too broad to be useful and should not compete with specific tests such as genetic testing, Pap smear, urinalysis, imaging studies, or named laboratory measurements.

## What changed

- Added `tests and testing` and `tests` to the blocked generic label list.
- Added the corresponding CUIs to the blocked generic CUI list:
  - `C0683443` - tests and testing
  - `C0022885` - Tests
- Added these labels to the generic label text constants so exact-label and primary-name boosts do not treat them as useful exact matches.
- Added a runtime ranker cutoff for blocked generic concepts so the current label index does not need to be rebuilt before the suppression takes effect.

## Impact

Future label-index builds will exclude these generic concepts by default, and current search ranking will remove them from result lists even if they are already present in the SQLite label index.

## Verification

- Confirmed the current label index contains:
  - `C0683443 | tests and testing`
  - `C0022885 | Tests`
- Verified helper suppression returns `True` for both concepts.
- Verified `rank_hits()` removes `C0683443` even when it is given an artificially high retrieval score, while preserving the specific `Genetic Testing` concept.
- Python syntax check passed using AST parsing without bytecode writes.
