# Human interventions log

Every point where a human was needed, in order. (Shown on the page as "where it needed a human".)

| Time (IST) | Step | What the human did | Why the agent couldn't |
|---|---|---|---|
| 18:35–18:50 | Planning | Set scope, approved plan v2, decided Composio usage policy | Product judgment / ownership |
| ~19:05 | S1 | Created Composio project API key (read all + session write/execute, least privilege) and filled `.env` with 4 keys | Account access and secrets are human-only |
| 18:50-19:00 | GO decisions | Approved each step (S1 onwards), then told the agent to keep going without per-step confirmation | Ownership of scope and pace |
| ~20:20 | Repo | Approved a private GitHub repo; commits use a noreply author email | Account ownership and privacy |
| 20:20-21:19 | Human audit | Blind-filled 90 claims (15 apps x 6) in data/truth.csv with source URLs, without seeing agent answers | Ground truth must be independent of the agent |
| 21:22 | Ship | Push and GitHub Pages deploy wait for the owner's OK | Publishing is outward-facing |
| 21:31 | Human audit | Corrected a data-entry slip in data/truth.csv: Salesforce auth held 'yes, Rest' (a public_api answer in the wrong row); now 'OAuth2' with source developer.salesforce.com quickstart-oauth. Re-scored at 21:32. | Only the human can amend their own ground truth |
