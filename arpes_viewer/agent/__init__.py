"""
agent/
======
ARPES viewer for AI agents: an MCP (Model Context Protocol) server that any
MCP-capable agent -- of any model -- can start and call.

- :mod:`agent.server` -- the tools and ``main()`` (``arpes-viewer-mcp``,
  ``python -m arpes_viewer.agent``).
- :mod:`agent.workspace` -- the headless data operations behind them.
- :mod:`agent.protocol` -- MCP's JSON-RPC over stdio, with no dependency.
- :mod:`agent.bridge` -- reaching the program open on screen (started with
  ``--agent-bridge``; its side is :mod:`ui.common.agentbridge`).

No Qt here.
"""
