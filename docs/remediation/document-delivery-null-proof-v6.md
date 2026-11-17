# Explicit null evidence arrays

Known completion evidence arrays distinguish an absent optional field from an explicitly supplied null. Null warnings, unmeasured details, checks, advisories or change summaries now fail closed instead of being omitted from a healthy document projection. The same validation applies to durable transcript replay. Missing optional fields retain their prior behavior.

Five projection regressions first failed. All 52 document-delivery tests, including two real transcript replay controls, then passed. Ruff, mypy and formatting passed. No wire fields, engine outcomes, model history, providers, permissions or storage fallback behavior changed.
