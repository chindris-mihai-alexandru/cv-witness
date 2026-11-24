# LinkedIn export as a safe My Profile MCP substitute

LinkedIn's official My Profile MCP server is partner-only. Its documented
model is still useful: read the member's own context, resolve named entities,
preview a change, and apply only after explicit member approval. cv-witness
can reproduce the safe parts locally from the candidate's own data export.

## What we copied, and what we did not

| My Profile MCP feature | cv-witness local equivalent | Boundary |
|---|---|---|
| `linkedin_get_profile_context` | `scripts/linkedin_export_import.py` builds a local snapshot from a user-supplied export zip/directory. | No network, no cookies, no other member's data. Sensitive fields (birth date, address, phone, maiden name) are excluded. |
| `linkedin_resolve_referenced_entities` | `scripts/linkedin_profile_diff.py` matches positions/projects/skills against the approved master and a private alias file. | Exact or candidate-approved aliases only. Unresolved entries are reported, never guessed. |
| `linkedin_preview_profile_section` | `render_preview()` writes a private markdown draft with checkboxes and source rows. | No approval envelope; no auto-approval; no profile write. |
| `linkedin_update_profile_section` | Not implemented. | The user applies changes manually in LinkedIn. We only provide a draft. |

## Workflow

1. In LinkedIn, request your own data export and download the archive.
2. Keep it private. Do not commit it or paste it into a public file.
3. Import only the selected files you are comfortable sharing with your agent:
   ```sh
   python3 scripts/linkedin_export_import.py ~/Downloads/linkedin-export.zip \
     --output ~/.cv-witness/linkedin-snapshot.json --json
   ```
4. Create a private alias file if your LinkedIn wording differs from the
   approved CV wording for the same dated role:
   ```json
   {
     "roles": {"Application Support Specialist": "IT Operations & Support Engineer"},
     "companies": {},
     "projects": {},
     "skills": {}
   }
   ```
5. Diff and preview:
   ```sh
   python3 scripts/linkedin_profile_diff.py ~/.cv-witness/linkedin-snapshot.json \
     --source foundation.md --provenance provenance.md \
     --aliases ~/.cv-witness/linkedin-aliases.json \
     --fields fields.json --json \
     --preview ~/.cv-witness/linkedin-update-preview.md
   ```
6. Review the preview. Any wording that reaches the CV or LinkedIn must still
   pass the truth test: Is it true? Is it you? Is it targeted?

## Edge cases covered

- ZIP and directory exports; nested CSV files; BOM and UTF-16 CSV.
- Missing files and unrecognized CSVs are reported, never silently dropped.
- Sensitive headers are excluded with a warning.
- Profile files with multiple rows keep the first and warn about the rest.
- Zip CSV count and size caps avoid accidental huge reads.
- Alias matching is explicit; token-order equivalence handles "Azure DevOps
  Engineer" against "DevOps Engineer (Azure)" without inventing a title.
- Draft wording is drawn only from the canonical CV fields file when supplied.

## Not supported

- No session-cookie or browser-automation LinkedIn MCP.
- No scraping, messaging, connecting, following, posting or profile editing.
- No reverse engineering of LinkedIn's partner-gated MCP endpoint.
- No claim that a local diff proves LinkedIn data is correct.

Official docs: <https://learn.microsoft.com/en-us/linkedin/consumer/integrations/mcp/profile-agent/overview>
