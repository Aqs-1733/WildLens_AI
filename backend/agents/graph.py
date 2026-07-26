from __future__ import annotations

from typing import TypedDict

try:
    from langgraph.graph import END, START, StateGraph
except ImportError:  # Core app keeps a local fallback if optional orchestration is unavailable.
    END = START = StateGraph = None  # type: ignore[assignment]


class EcoAgentState(TypedDict, total=False):
    question: str
    species_id: int | None
    job_id: int | None
    route: str
    agent_notes: list[str]


def _route_agent(state: EcoAgentState) -> EcoAgentState:
    question = state.get("question", "")
    if any(word in question for word in ("风险", "火", "烟", "人员", "预警", "危险")):
        route = "risk"
    elif any(word in question for word in ("视频", "画面", "几只", "出现", "行为", "置信度")):
        route = "observation"
    elif any(word in question for word in ("学习", "挑战", "星", "奖励", "收集")):
        route = "learning"
    else:
        route = "taxonomy"
    return {"route": route, "agent_notes": [f"Router Agent → {route}"]}


def _taxonomy_agent(state: EcoAgentState) -> EcoAgentState:
    notes = list(state.get("agent_notes", []))
    notes.append("Taxonomy Agent：核对中文名、拉丁学名与分类层级")
    return {"agent_notes": notes}


def _observation_agent(state: EcoAgentState) -> EcoAgentState:
    notes = list(state.get("agent_notes", []))
    notes.append("Observation Agent：读取当前视频目标、时间戳和追踪编号")
    return {"agent_notes": notes}


def _risk_agent(state: EcoAgentState) -> EcoAgentState:
    notes = list(state.get("agent_notes", []))
    notes.append("Risk Agent：区分可观察事实、规则触发与待复核推测")
    return {"agent_notes": notes}


def _learning_agent(state: EcoAgentState) -> EcoAgentState:
    notes = list(state.get("agent_notes", []))
    notes.append("Learning Agent：给出可完成的科普挑战与保护行动")
    return {"agent_notes": notes}


def _next_node(state: EcoAgentState) -> str:
    return state.get("route", "taxonomy")


def _build_graph():
    if StateGraph is None:
        return None
    builder = StateGraph(EcoAgentState)
    builder.add_node("router", _route_agent)
    builder.add_node("taxonomy", _taxonomy_agent)
    builder.add_node("observation", _observation_agent)
    builder.add_node("risk", _risk_agent)
    builder.add_node("learning", _learning_agent)
    builder.add_edge(START, "router")
    builder.add_conditional_edges(
        "router",
        _next_node,
        {
            "taxonomy": "taxonomy",
            "observation": "observation",
            "risk": "risk",
            "learning": "learning",
        },
    )
    for node in ("taxonomy", "observation", "risk", "learning"):
        builder.add_edge(node, END)
    return builder.compile()


GRAPH = _build_graph()


def orchestrate(question: str, species_id: int | None, job_id: int | None) -> EcoAgentState:
    initial: EcoAgentState = {
        "question": question,
        "species_id": species_id,
        "job_id": job_id,
        "agent_notes": [],
    }
    if GRAPH is not None:
        return GRAPH.invoke(initial)
    routed = _route_agent(initial)
    state = {**initial, **routed}
    nodes = {
        "taxonomy": _taxonomy_agent,
        "observation": _observation_agent,
        "risk": _risk_agent,
        "learning": _learning_agent,
    }
    return {**state, **nodes[state["route"]](state)}
