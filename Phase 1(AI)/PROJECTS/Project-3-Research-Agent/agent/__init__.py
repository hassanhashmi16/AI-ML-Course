"""Agent: the hand-rolled reasoning loop and everything it needs to run.

`state.py` defines the shared `AgentState`; `llm.py`, `loop.py`, `checkpoint.py`,
and `policy.py` each operate on that one type. Keeping the loop and its
dependencies in a single package is what lets Project 4 replace this whole
package with LangGraph at one boundary.
"""
