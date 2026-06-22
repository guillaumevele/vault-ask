# vault-ask

[![CI](https://github.com/guillaumevele/vault-ask/actions/workflows/ci.yml/badge.svg)](https://github.com/guillaumevele/vault-ask/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)
[![Zero dependencies](https://img.shields.io/badge/dependencies-zero-success.svg)](pyproject.toml)

**Ask your Obsidian vault. Get cited answers. Never hallucinate.**

A tiny (~300-line, dependency-free) grounded question-answering tool over a folder
of Markdown notes. It finds the relevant notes, asks *your* LLM to answer **only**
from them, forces a `[[wikilink]]` citation on every claim, and **refuses instead
of guessing** when the answer isn't in your vault.

```console
$ vault-ask "what did I decide about the pricing model?"
Q: what did I decide about the pricing model?

Flat 49 EUR/month, no per-seat pricing, decided after the churn analysis.
[[Decisions/2026-Pricing|2026-Pricing]]

Notes consulted:
- [[Decisions/2026-Pricing|2026-Pricing]]
- [[Meetings/2026-01-pricing-review|2026-01-pricing-review]]
```

Ask something that isn't in your notes and it won't make anything up:

```console
$ vault-ask "what is my bank account number?"
Q: what is my bank account number?

No note in the vault answers this question.
```

## Why

A second brain is only useful if knowledge comes *back out*. Most "chat with your
notes" tools either need a vector database and an indexing pipeline, or happily
hallucinate plausible answers — a dealbreaker when your notes are medical, legal,
or financial. `vault-ask` is the opposite: zero index, zero database, and a hard
refusal guarantee. It runs `ripgrep` over your vault, ranks notes by term rarity
(TF-IDF), and hands the best excerpts to whatever LLM you already use.

## How it works

1. **Candidate search** — `ripgrep` scans the whole vault in milliseconds.
2. **IDF ranking** — notes are scored by the *rarity* of the query terms they
   contain, so a rare, specific word (a project codename) outweighs a word that
   appears in hundreds of notes. No embeddings, no index, no warm-up.
3. **Focused excerpts** — only the headings and matching lines of the top notes
   are sent to the model (notes can be long).
4. **Grounded prompt** — the model must cite each claim as a `[[link]]`, must not
   add outside knowledge, and must reply with a fixed refusal sentence if the
   excerpts don't answer the question.
5. **Robust refusal check** — a refusal (even reworded by the model) is never
   dressed up as a sourced answer; its citations are stripped.

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
decisions, numbers, names, "what did I say about …". It's fast and it never lies.

**Not good at:** abstract questions whose vocabulary differs from your notes (you
ask "my funding strategy", the note says "tax credit"). That's the inherent limit
of keyword retrieval — proper semantic recall needs embeddings, which this tool
deliberately avoids to stay zero-dependency and zero-index. When it can't match,
it refuses honestly rather than guessing.

## Tests

```bash
python3 -m unittest discover -s tests
```

## License

MIT — see [LICENSE](LICENSE).
