"""The investigation graph: LangGraph owns the loop, our nodes own the strategy.

Same shape as any agent graph, and deliberately readable:

    START -> investigate -> (tools ->) grade -> investigate | synthesize -> END

LangGraph provides execution, branching, and message merging; Project 3's
handwritten loop and dispatcher are gone. The interesting decisions remain
ours: what the investigator is told, what counts as sufficient evidence,
when to stop, and how the report is assembled.
"""

from __future__ import annotations

from functools import partial

from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from agent.nodes import (
    Sufficiency,
    grade_evidence,
    investigate,
    route_after_grade,
    route_after_investigate,
    run_tools,
    synthesize,
)
from agent.state import InvestigationState
from agent.tools import ToolContext, build_tools
from generation.answer import build_llm


def build_graph(context: ToolContext):
    """Compile the investigation graph bound to one run's context."""
    tools = build_tools(context)
    tool_node = ToolNode(tools)
    llm = build_llm()
    llm_with_tools = llm.bind_tools(tools)
    grader = build_llm().with_structured_output(Sufficiency)

    builder = StateGraph(InvestigationState)
    builder.add_node("investigate", partial(investigate, llm_with_tools=llm_with_tools))
    builder.add_node("tools", partial(run_tools, tool_node=tool_node, context=context))
    builder.add_node("grade", partial(grade_evidence, grader=grader))
    builder.add_node("synthesize", partial(synthesize, context=context, llm=llm))

    builder.add_edge(START, "investigate")
    builder.add_conditional_edges(
        "investigate",
        route_after_investigate,
        {"tools": "tools", "grade": "grade"},
    )
    builder.add_edge("tools", "grade")
    builder.add_conditional_edges(
        "grade",
        route_after_grade,
        {"investigate": "investigate", "synthesize": "synthesize"},
    )
    builder.add_edge("synthesize", END)
    return builder.compile()
