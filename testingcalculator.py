from typing import Literal

from dotenv import load_dotenv
load_dotenv()

from langchain_core.tools import tool
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI

from langgraph.graph import StateGraph, MessagesState, START, END
from langgraph.prebuilt import ToolNode


# =========================
# 1. Define tools
# =========================

@tool
def add(a: float, b: float) -> float:
    """Add two numbers."""
    return a + b


@tool
def subtract(a: float, b: float) -> float:
    """Subtract b from a."""
    return a - b


@tool
def multiply(a: float, b: float) -> float:
    """Multiply two numbers."""
    return a * b


@tool
def divide(a: float, b: float) -> float:
    """Divide a by b."""
    if b == 0:
        raise ValueError("Cannot divide by zero.")
    return a / b


tools = [
    add,
    subtract,
    multiply,
    divide,
]


# =========================
# 2. Create LLM
# =========================

llm = ChatOpenAI(
    model="gpt-4.1-mini",
    temperature=0,
)

# Tell the model which tools it can use
llm_with_tools = llm.bind_tools(tools)


# =========================
# 3. Agent node
# =========================

def agent_node(state: MessagesState):
    """
    LLM reads conversation history and decides:
    1. call a tool
    2. or directly answer
    """

    response = llm_with_tools.invoke(state["messages"])

    return {
        "messages": [response]
    }


# =========================
# 4. Decide next step
# =========================

def should_continue(
    state: MessagesState,
) -> Literal["tools", END]:

    last_message = state["messages"][-1]

    # LLM requested one or more tools
    if last_message.tool_calls:
        return "tools"

    # No tool call -> finished
    return END


# =========================
# 5. Tool node
# =========================

tool_node = ToolNode(tools)


# =========================
# 6. Build LangGraph
# =========================

builder = StateGraph(MessagesState)

builder.add_node(
    "agent",
    agent_node,
)

builder.add_node(
    "tools",
    tool_node,
)


# START -> Agent
builder.add_edge(
    START,
    "agent",
)


# Agent decides:
#
# agent -> tools
# or
# agent -> END
builder.add_conditional_edges(
    "agent",
    should_continue,
)


# After tool execution:
#
# tools -> agent
builder.add_edge(
    "tools",
    "agent",
)


# Compile graph
graph = builder.compile()


# =========================
# 7. Run agent
# =========================

if __name__ == "__main__":

    question = input("You: ")

    result = graph.invoke(
        {
            "messages": [
                HumanMessage(
                    content=question
                )
            ]
        }
    )

    # Show every step, including tool calls and tool results
    for message in result["messages"]:
        message.pretty_print()

    final_message = result["messages"][-1]

    print("\nAgent:")
    print(final_message.content)