# vault-ask

[![CI](https://github.com/guillaumevele/vault-ask/actions/workflows/ci.yml/badge.svg)](https://github.com/guillaumevele/vault-ask/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)
[![Zero dependencies](https://img.shields.io/badge/dependencies-zero-success.svg)](pyproject.toml)

**Ask your Obsidian vault with fail-closed citation validation.**

A small, dependency-free question-answering tool over a folder of Markdown notes.
It finds relevant notes, asks *your* LLM to answer only from those excerpts, and
fails closed unless the output contains an exact `[[wikilink]]` copied from the
selected source set.

```console
$ vault-ask "what did I decide about the pricing model?"
Q: what did I decide about the pricing model?

Flat 49 EUR/month, no per-seat pricing, decided after the churn analysis.
[[Decisions/2026-Pricing|2026-Pricing]]

Notes consulted:
- [[Decisions/2026-Pricing|2026-Pricing]]
- [[Meetings/2026-01-pricing-review|2026-01-pricing-review]]
```

When the model emits the fixed refusal, returns no citation, or cites an
unselected note, the validator returns the canonical refusal instead:

```console
$ vault-ask "what is my bank account number?"
Q: what is my bank account number?

No note in the vault answers this question.
```

## Why

A second brain is only useful if knowledge comes *back out*. Many "chat with your
notes" tools require a vector database and an indexing pipeline. `vault-ask`
instead uses no index or database: it runs `ripgrep` over your vault, ranks notes
by term rarity, and hands focused excerpts to whatever LLM you already use.

## How it works

1. **Candidate search** — `ripgrep` scans the whole vault in milliseconds.
2. **IDF ranking** — notes are scored by the *rarity* of the query terms they
   contain, so a rare, specific word (a project codename) outweighs a word that
   appears in hundreds of notes. No embeddings, no index, no warm-up.
3. **Focused excerpts** — only the headings and matching lines of the top notes
   are sent to the model (notes can be long).
4. **Constrained prompt** — the model is instructed to cite its claims, avoid
   outside knowledge, and emit a fixed refusal when evidence is insufficient.
5. **Fail-closed output check** — a non-refusal answer is accepted only when it
   contains at least one exact citation from the selected notes. Unknown or
   missing citations produce the fixed refusal.

This is a mechanical provenance check, not semantic entailment verification. A
valid citation proves which selected note was referenced; it does not prove that
the note supports every sentence in the answer.

In JSON output, the backward-compatible `grounded` field now means that exact
selected-source citation validation passed. It does not mean semantic entailment
was evaluated. Arbitrary paraphrases of refusal cannot be detected mechanically
when they also contain a valid selected-source citation.

Nothing leaves your machine except what your own LLM command chooses to send.

## Install

Requires **Python 3.9+** and **[ripgrep](https://github.com/BurntSushi/ripgrep)**
(`rg`) on your `PATH`.

```bash
# pip (installs the `vault-ask` command)
pip install git+https://github.com/guillaumevele/vault-ask.git
```

Or run it as a single file, no install:

```bash
git clone https://github.com/guillaumevele/vault-ask.git
cd vault-ask
python3 vault_ask.py "your question"
```

No dependencies beyond the Python standard library and ripgrep.

## Configure your LLM

`vault-ask` shells out to whatever LLM command you set in `VAULT_ASK_LLM`. The
prompt is piped on **stdin** by default, or substituted for `{prompt}` if the
command contains that placeholder.

```bash
# Local model via Ollama (prompt on stdin):
export VAULT_ASK_LLM='ollama run llama3.1'

# Simon Willison's `llm` CLI (any provider it supports):
export VAULT_ASK_LLM='llm -m gpt-4o-mini'

# A CLI that takes the prompt as an argument — use the {prompt} placeholder:
export VAULT_ASK_LLM='your-llm-cli --prompt {prompt}'
```

Point it at your vault once:

```bash
export OBSIDIAN_VAULT="$HOME/Obsidian/MyVault"
```

## Usage

```bash
vault-ask "what did I decide about X?"
vault-ask --vault ~/notes "when is the contract renewal?"
vault-ask --limit 8 --json "summarize my pricing decisions"
```

No LLM? Use `--sources-only` to just rank the most relevant notes — a smart grep
for your vault that needs no model at all:

```bash
vault-ask --sources-only "pricing model"
# Most relevant notes for: pricing model
# - [[Decisions/2026-pricing|2026-pricing]]
# - [[Meetings/2026-01-pricing-review|2026-01-pricing-review]]
```

| Flag | Default | Description |
|------|---------|-------------|
| `--vault` | `$OBSIDIAN_VAULT` or `.` | path to the vault |
| `--limit` | `5` | max notes to consult |
| `--llm` | `$VAULT_ASK_LLM` | LLM command (overrides env) |
| `--sources-only` | off | rank relevant notes, no LLM call |
| `--json` | off | raw structured output |
| `--version` | | print version |

## What it's good at — and what it isn't

**Good at:** factual lookups where the words of your question point at a note —
decisions, numbers, names, "what did I say about …" — with selected-source
citation validation and explicit abstention states.

**Not good at:** abstract questions whose vocabulary differs from your notes (you
ask "my funding strategy", the note says "tax credit"). Keyword retrieval can
miss semantically related notes, and an allowed citation can still accompany an
unsupported claim. Semantic recall and entailment verification are outside this
zero-dependency tool's current scope.

## Tests

```bash
python3 -m unittest discover -s tests
```

## Related

[**voice-to-vault**](https://github.com/guillaumevele/voice-to-vault) is the other
half of the loop: it routes your voice captures into the Obsidian vault that
`vault-ask` then answers questions about. One files your thoughts, the other
brings them back.

## License

MIT — see [LICENSE](LICENSE).
