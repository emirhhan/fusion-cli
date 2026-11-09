# Catalogue, gameplay, and source consistency continuation

The source changes in this slice do not update the installed application.

## Catalogue

`runtime.agent_catalog_chars` defaults to zero, preserving full descriptions. A positive budget applies only when the current request permits `find_agent`. Every permitted name remains discoverable; if names alone exceed the budget, the response explicitly says so. Exact description pages load metadata, recheck current launch authority, and exclude disabled legacy fallback descriptors. Agent bodies still load on launch.

A synthetic 12-descriptor production-renderer fixture measured 101,589 full characters against 2,200 budgeted characters. This is not evidence of model latency or quality improvement. The default remains unchanged. Catalogue and agent-loop regression group: 201 tests passed. Python and general code reviews approved after the hidden legacy fallback finding was reproduced and fixed.

## Requested game controls

A real model produced a playable offline game. Independent browser play confirmed keyboard and touch movement, catches increasing score, three misses ending the game, and restart. The explicitly requested visible pause button was missing. A later model repair added a visible button without connecting it to gameplay. Neither output was accepted as complete.

The production probe now derives the narrow pause requirement from the accepted request owner, excluding quoted, optional, and negative requests. It checks actual visible, enabled controls, clicks Pause, and observes known pause/resume state transitions. Unknown hooks return an unverified warning before any click. The complete optional control measurement has a four-second deadline. Strict actionability is shared between presence and behavior; unrelated Continue buttons do not suppress a working toggle fallback. The actual `play_probe` tool and the final verifier use the same requirement, so the actor receives failures before closing.

This does not prove every game mechanic. The existing console, animation, keyboard, HUD, and conditional end/restart checks retain their own scope. Reviewer findings about negation, transparency, duplicate controls, resume selection, and unknown-hook state contamination were reproduced and corrected with browser regressions.

## Reader metadata

Four real NIM judge cases used an actual production `web_fetch` receipt from the official Python 3.12.0 release page. The faithful multi-claim report passed; an incorrect release date and unsupported current-latest claim were rejected. Honest truncation disclosure was initially rejected because the judge could not cite metadata with an exact span.

Owned receipt metadata now has a citable `sN:receipt` span containing only reader URL, access time, completeness, and scope. Existing owner and digest admission remain mandatory. The judge is instructed that this metadata supports fetch-scope statements, not page facts. The same four cases then matched all four expected decisions. This is a bounded public-source calibration, not native UI or exhaustive research acceptance.

The game/source/scope regression group passed 166 tests before final packaging. Security review found no new authority or transport in the receipt change. General code review approved the final source slice.
