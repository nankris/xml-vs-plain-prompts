# XML tags vs plain prose in a Claude Code prompt: no difference worth the brackets

*Draft. Tech in General experiment #094. 28 headless Claude Code runs (Haiku 5.5), 2026-10-15 IST.*

Same four instructions, two ways: as a plain sentence, or as `<task>` / `<constraints><rule>` / `<output_format>` XML. 14 small bug fixes each.

- Both fixed 14/14.
- Both followed "reply with one line" 14/14.
- XML wrote a bit less on 12 of 14 tasks (about 40 tokens), but two XML runs rambled, so the averages came out even.
- Cost for all 14: 4.79¢ vs 4.82¢.

**Takeaway.** For short instructions, write them however reads best to you. Structure probably matters more when a prompt mixes long instructions with pasted data, which this didn't test.

*$ are API-equivalent estimates; Pro isn't billed per token.*
