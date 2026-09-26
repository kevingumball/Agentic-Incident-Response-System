"""ReAct-style baseline.

A single LLM agent iteratively selects observability tools based on tool
outputs until it produces a root-cause diagnosis, without explicit planner,
hypothesis tracking, or verifier nodes. (Same loop as the calculator agent in
testingcalculator.py, with incident tools.)

START -> agent -> tools? --yes--> tools -> agent
                        --no---> diagnose -> END

Same model, same MCP tools, same step budget and same output format
(Diagnosis) as the main system; only the graph structure differs.
"""

from __future__ import annotations

from typing import Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode

from agent import config, prompts
from agent.graph import make_llm
from agent.schemas import Diagnosis


class ReActState(MessagesState):
    diagnosis: dict


def count_tool_calls(messages) -> int:
    return sum(1 for m in messages if isinstance(m, ToolMessage))


class ReActAgent:
    def __init__(self, read_tools: list[BaseTool], llm: ChatOpenAI | None = None, max_steps: int = config.MAX_STEPS):
        llm = llm or make_llm()
        self.read_tools = read_tools
        self.max_steps = max_steps
        self.llm_with_tools = llm.bind_tools(read_tools, parallel_tool_calls=False)
        self.diagnosis_llm = llm.with_structured_output(Diagnosis, method="function_calling")

    async def agent(self, state: ReActState) -> dict:
        response = await self.llm_with_tools.ainvoke([SystemMessage(prompts.REACT_SYSTEM), *state["messages"]])
        return {"messages": [response]}

    def should_continue(self, state: ReActState) -> Literal["tools", "diagnose"]:
        last = state["messages"][-1]
        if isinstance(last, AIMessage) and last.tool_calls and count_tool_calls(state["messages"]) < self.max_steps:
            return "tools"
        return "diagnose"

    async def diagnose(self, state: ReActState) -> dict:
        messages = list(state["messages"])
        # Drop a trailing tool request that the step budget did not allow to run.
        if isinstance(messages[-1], AIMessage) and messages[-1].tool_calls:
            messages = messages[:-1]
        d: Diagnosis = await self.diagnosis_llm.ainvoke(
            [SystemMessage(prompts.REACT_SYSTEM), *messages, HumanMessage(prompts.DIAGNOSIS_REQUEST)]
        )
        return {"diagnosis": d.model_dump()}

    def build(self):
        g = StateGraph(ReActState)
        g.add_node("agent", self.agent)
        g.add_node("tools", ToolNode(self.read_tools))
        g.add_node("diagnose", self.diagnose)
        g.add_edge(START, "agent")
        g.add_conditional_edges("agent", self.should_continue)
        g.add_edge("tools", "agent")
        g.add_edge("diagnose", END)
        return g.compile()
