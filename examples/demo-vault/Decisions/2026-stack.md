---
tags: [decision, engineering]
date: 2026-02-03
---
# Backend stack

We standardised on **Postgres** for primary storage and **ripgrep** for the
local search index prototype. We explicitly avoided adding a vector database
for now — keyword search covers the current corpus.
