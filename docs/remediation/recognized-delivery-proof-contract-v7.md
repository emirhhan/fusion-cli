# Recognized completion evidence contract

Known typed critical fields distinguish absence from malformed values. Explicit null criteria, status totals, suspicious-test metadata and truncation flags fail closed. Optional fields may remain absent; verified itself retains its explicit nullable state. Required verification and list fields must be present.

Tamper counts are nonnegative safe integers; weakening cannot exceed total. Positive nonweakening findings downgrade a verified result to unknown, and any tamper metadata prevents the document presentation marker. Criterion totals cannot be smaller than retained criteria or recognized status totals; status sums must remain safe integers. Unknown extra fields remain ignored.

Validation: 85 document-delivery tests passed, including six actual durable replay null controls and positive absent/false/zero controls. Fourteen newly failing typed-field/count tests were reproduced before fixes. Ruff, formatting, mypy and diff checks passed. A 28-case raw → public projection → durable replay fixture matrix is saved in the task's document-delivery-backend-v6 work directory for independent frontend verification. Canonical invalid problem rows may normalize verified null to false on replay; they remain blocking, preserve false claims and never acquire a document marker.
