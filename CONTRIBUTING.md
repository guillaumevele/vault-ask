# Contributing

Thanks for your interest in vault-ask. It's intentionally small and
dependency-free — please keep it that way.

## Principles

- **Zero runtime dependencies** beyond the Python standard library and `ripgrep`.
  No vector database, no embedding model, no network calls of our own (only your
  configured LLM command talks to the outside world).
- **Never fabricate.** The refusal guarantee is the core promise. Any change to
  retrieval or prompting must preserve: mandatory `[[citations]]`, and an honest
  refusal when the excerpts don't support an answer.

## Development

```bash
git clone https://github.com/guillaumevele/vault-ask.git
cd vault-ask
python -m unittest discover -s tests -v
```

Tests must pass on Python 3.9+ and require `ripgrep` on your `PATH`.

## Pull requests

- Add or update tests for any behaviour change.
- Keep the public CLI and the result schema stable where possible.
- Run the test suite before opening a PR.

## Ideas welcome

- Optional semantic retrieval (embeddings) as a *separate, opt-in* mode that keeps
  the default zero-dependency.
- Adapters/examples for more LLM CLIs.
- Better excerpt selection.
