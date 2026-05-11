# Remove Topbar Header

## Change

Removed the `header` / `.topbar` block from `docs/search_quality_server.html`.

## Result

The search page no longer spends vertical space on the duplicated `UMLS 2.0` title/status header. The main search panel now starts at the top of the page. The JavaScript status updater already guards against a missing `#status` element, so this does not remove search functionality.

## Verification

- Confirmed the targeted markup was removed from `docs/search_quality_server.html`.
