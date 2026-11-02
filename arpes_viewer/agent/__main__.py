"""``python -m arpes_viewer.agent``: the MCP server on stdin/stdout."""
import sys

from arpes_viewer.agent.server import main

sys.exit(main())
