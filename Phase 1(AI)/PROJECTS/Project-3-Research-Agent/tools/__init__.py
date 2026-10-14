"""Tools: everything the agent can *do*, behind one registry.

Each tool module (web_search, fetch_page, notes, brief — Steps 4-7) defines a
plain function and registers it with `tools.registry`. Nothing in this package
knows about the agent loop; the loop only knows the registry. That one-way
dependency is what keeps a tool addition a pure addition.
"""
