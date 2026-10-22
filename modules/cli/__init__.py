"""Command line interface of the control center.

    kutral_mgr.py  ->  parser and dispatch
    environment.py ->  builds the environment (real or rehearsal) and demands the adapters
    commands.py    ->  one function per command, no printing: they return data

The separation is deliberate: the commands return dictionaries, and the CLI is what
prints them. That way the same command serves the text output, `--json` and the tests,
without rewriting the logic.
"""
