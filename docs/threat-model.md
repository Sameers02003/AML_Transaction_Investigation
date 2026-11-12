# Threat model (learning project)

## Assets
Transactions, customer profiles, alerts, case notes, audit log, rule definitions, model files.

## Roles
| Action | analyst | senior | compliance | admin | auditor |
|---|---|---|---|---|---|
| Read alerts, cases, customers | yes | yes | yes | yes | yes (account numbers masked in lists) |
| Assign alerts, create cases, add notes | yes | yes | yes | yes | no |
| Close with false positive / explainable | yes | yes | yes | yes | no |
| Escalate | requests | approves | approves | no | no |
| Create new rule versions | no | no | yes | yes | no |

## Threats and mitigations
| Threat | Mitigation |
|---|---|
| Stolen or guessed login | bcrypt password hashes, 10 login attempts per minute, tokens expire after 8 hours |
| Unauthorised change | Role checks on every endpoint, tested; read-only auditor role |
| Tampering with history | Audit table is append-only (database triggers); rule edits create new versions |
| Duplicate or malformed events | API key on ingestion, schema validation, unique event IDs, dead-letter topic |
| Data in logs or repo | Account numbers masked in logs; payloads not logged; .env and model files are git-ignored; data is synthetic |

## Not implemented (would be required in production)
MFA, TLS, a secrets manager, encryption at rest, data retention and deletion rules, sanctions screening, formal model validation, and automatic regulatory filing (deliberately excluded: dispositions are separate from filings).