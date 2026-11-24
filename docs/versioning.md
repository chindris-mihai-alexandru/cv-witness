# Versioning

cv-witness is stable as of 1.0.0. The public contract is the canonical template
placeholder set, the field JSON schema, the CLI JSON shapes, and the advisory
versus hard-gate semantics documented in `SKILL.md` and `README.md`.

- **Patch** (`1.0.1`): bug fix that preserves schemas, CLI output shapes and gate behavior.
- **Minor** (`1.1.0`): new compatible script, flag, reference or provider.
- **Major** (`2.0.0`): breaking template/field change, CLI contract change, or a change to privacy/safety guarantees that users must act on.

Do not renumber existing releases. The 0.x history records the experimental
period and stays intact. Group related work into one release rather than
tagging every session; issue a patch immediately only for a user-visible
regression.
