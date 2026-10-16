# #094 XML-tagged vs plain prompts (Claude Code CLI, Haiku 5.5)

**Question.** Same instructions, written as plain prose or wrapped in XML tags (`<task>`, `<constraints><rule>`, `<output_format>`). Does structure change tokens or accuracy?

**Short answer.** Not in any way that matters. 14 tasks × 2 = 28 runs, **14/14 passed in both arms**, and **14/14 final replies were one line in both** (the format instruction was followed either way). XML produced *fewer* output tokens on **12 of 14 tasks** (median −40 tokens, ≈ −7%), but two runs went long (N03_csv +775, T05_stale +483), so the mean was +5% (745 vs 708). API-equivalent cost: $0.0479 vs $0.0482 for all 14 tasks. Turns and tool calls were the same (5.4–5.5, 4.4–4.5). Call it a wash with a slight tilt toward XML on typical runs.

## Setup
- Claude Code 2.1.300, `--model haiku` (claude-haiku-5-5), default effort, Pro; headless `claude -p "$(cat scripts/<arm>.txt)" --output-format stream-json --verbose --dangerously-skip-permissions --strict-mcp-config --no-session-persistence`, fresh copy of one SUITE14 package per run.
- `scripts/plain.txt` and `scripts/xml.txt` carry identical instructions (fix so `node test.js` passes, don't edit test.js, smallest change, run the test, reply with one line).
- Tasks: all 14 SUITE14 packages (N01–N03, T01–T11). 1 run per cell, 2 at a time, 2026-10-14 ~20:09–20:11 UTC.
- **Why Haiku:** the Pro 5-hour window was at 93% when this ran; Haiku barely moves it. Plan row asked for 20 tasks; 14 is the whole fixture set. An Opus arm was not run.
- Est. $ = `total_cost_usd` — **API-equivalent estimate; Pro isn't billed per token.**

## Exact commands
```bash
source /workspace/tools/setup.sh
scripts/harness/driver_cc.sh scripts/jobs.txt 2 results/driver.log
/workspace/tools/mlenv/bin/python scripts/analyze.py
```

## Results
| Arm | Passed | One-line final reply | Output tokens (mean) | Total tokens (mean) | Model calls | Tool calls | Est. $ (14 tasks) |
|---|---|---|---|---|---|---|---|
| plain | 14/14 | 14/14 | 708 | 79,657 | 5.5 | 4.5 | $0.0482 |
| XML | 14/14 | 14/14 | 745 | 81,975 | 5.4 | 4.4 | $0.0479 |

Paired per task (XML − plain output tokens): median −40; XML lower on 12/14; outliers N03_csv +775, T05_stale +483. Chart: `results/chart.png`. Data: `results/runs.csv`, `results/summary.csv`.

## Caveats
- Short instructions (4 rules). XML tags are meant to help with long prompts that mix instructions, data and examples; that's untested here.
- One run per cell and one model; the two outliers are probably ordinary run-to-run variation in how much Haiku explains, not the tags.
