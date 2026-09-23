"""mcp-fanout: a reproducible measurement harness for MCP tool-call fan-out.

The package is split so the measurement CORE (shingle, redact, match, classify, record,
aggregate) depends only on the standard library and is the part CI runs. The capture layer
(driver, capture_addon) needs the optional 'capture' extra (mitmproxy, PyYAML) and is only
used to produce a run, never to compute a number from one.
"""

__version__ = "1.0.0rc3"
