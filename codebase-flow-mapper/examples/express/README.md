# Example: expressjs/express, mapped from a context pack alone

This page was produced the "chat only" way, to show that the pipeline works on a real project and not just the demo:

1. `codeflow.py pack <express clone> --max-chars 30000` (about 7k tokens)
2. A model read only that pack and wrote `spec.json` (the file next to this one)
3. `codeflow.py render spec.json --repo <express clone> --strict` verified that all 26 cited paths exist

What it shows and doesn't: the model never opened Express's source beyond the excerpts in the pack, so
roles of the files in `lib/` are marked **inferred** (dashed) on the page rather than asserted. That is the intended
behaviour when evidence is thin. Treat this as a demonstration of the workflow, not as documentation of Express.

Express is MIT-licensed (c) its contributors: https://github.com/expressjs/express
The page needs an internet connection to draw its diagrams (it loads Mermaid from a CDN).
