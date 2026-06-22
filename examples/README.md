# Demo vault

A tiny three-note vault to try `vault-ask` in 30 seconds.

```bash
export VAULT_ASK_LLM='ollama run llama3.1'   # or any LLM CLI you have

vault-ask --vault examples/demo-vault "what pricing model did we choose and why?"
# -> Flat 49 EUR/month, no per-seat (it punished team accounts that drive
#    retention). [[Decisions/2026-pricing|2026-pricing]]

vault-ask --vault examples/demo-vault "what database did we pick?"
# -> Postgres, with ripgrep for the local search prototype; no vector DB yet.
#    [[Decisions/2026-stack|2026-stack]]

vault-ask --vault examples/demo-vault "what is our refund policy?"
# -> No note in the vault answers this question.   (honest refusal)
```
