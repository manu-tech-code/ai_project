"""
Unit tests for app.agents.smell_detector.SmellDetectorAgent.

Tests cover the rule-based smell detectors directly and the agent as a whole.
DB operations are mocked with AsyncMock.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agents.smell_detector import SmellDetectorAgent, SmellResult, _compute_loc
from app.adapters.base import UCGNodeRaw, UCGEdgeRaw


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------


def _make_ucg_node(
    node_type: str,
    name: str,
    line_start: int = 1,
    line_end: int = 10,
    properties: dict | None = None,
) -> MagicMock:
    """Build a mock UCGNode that behaves like the ORM model."""
    node = MagicMock()
    node.id = uuid.uuid4()
    node.node_type = node_type
    node.qualified_name = f"com.example.{name}"
    node.language = "java"
    node.line_start = line_start
    node.line_end = line_end
    node.properties = properties or {}
    return node


def _make_ucg_edge(edge_type: str, source_id, target_id) -> MagicMock:
    edge = MagicMock()
    edge.id = uuid.uuid4()
    edge.edge_type = edge_type
    edge.source_node_id = source_id
    edge.target_node_id = target_id
    edge.weight = 1.0
    return edge


def _make_agent() -> SmellDetectorAgent:
    return SmellDetectorAgent()


# ---------------------------------------------------------------------------
# _compute_loc helper
# ---------------------------------------------------------------------------


def test_compute_loc_with_valid_lines():
    node = _make_ucg_node("CLASS", "Foo", line_start=1, line_end=100)
    assert _compute_loc(node) == 100


def test_compute_loc_single_line():
    node = _make_ucg_node("CLASS", "Foo", line_start=5, line_end=5)
    assert _compute_loc(node) == 1


def test_compute_loc_none_lines():
    node = _make_ucg_node("CLASS", "Foo", line_start=None, line_end=None)
    assert _compute_loc(node) == 0


def test_compute_loc_only_start():
    node = _make_ucg_node("CLASS", "Foo", line_start=10, line_end=None)
    assert _compute_loc(node) == 0


# ---------------------------------------------------------------------------
# God class detector
# ---------------------------------------------------------------------------


def test_god_class_detected_when_methods_exceed_threshold():
    """A class with 12 CONTAINS->METHOD edges should trigger god class."""
    agent = _make_agent()

    cls = _make_ucg_node("CLASS", "OrderService")
    methods = [_make_ucg_node("METHOD", f"method{i}") for i in range(12)]
    node_by_id = {cls.id: cls, **{m.id: m for m in methods}}

    # Build CONTAINS edges from class to each method
    outgoing = {
        cls.id: [
            _make_ucg_edge("CONTAINS", cls.id, m.id)
            for m in methods
        ]
    }

    results = agent._detect_god_class([cls], outgoing, node_by_id)

    assert len(results) == 1
    assert results[0].smell_type == "god_class"
    assert results[0].severity == "high"
    assert results[0].evidence["method_count"] == 12


def test_god_class_not_detected_below_threshold():
    """A class with exactly 10 methods should NOT trigger god class (threshold is >10)."""
    agent = _make_agent()

    cls = _make_ucg_node("CLASS", "SmallClass")
    methods = [_make_ucg_node("METHOD", f"method{i}") for i in range(10)]
    node_by_id = {cls.id: cls, **{m.id: m for m in methods}}
    outgoing = {
        cls.id: [_make_ucg_edge("CONTAINS", cls.id, m.id) for m in methods]
    }

    results = agent._detect_god_class([cls], outgoing, node_by_id)
    assert len(results) == 0


def test_god_class_non_method_contains_edges_ignored():
    """CONTAINS edges to FIELD nodes should not count as methods."""
    agent = _make_agent()

    cls = _make_ucg_node("CLASS", "Foo")
    fields = [_make_ucg_node("FIELD", f"field{i}") for i in range(15)]
    node_by_id = {cls.id: cls, **{f.id: f for f in fields}}
    outgoing = {
        cls.id: [_make_ucg_edge("CONTAINS", cls.id, f.id) for f in fields]
    }

    results = agent._detect_god_class([cls], outgoing, node_by_id)
    assert len(results) == 0


# ---------------------------------------------------------------------------
# Large class detector
# ---------------------------------------------------------------------------


def test_large_class_detected_above_300_loc():
    agent = _make_agent()
    cls = _make_ucg_node("CLASS", "HugeClass", line_start=1, line_end=350)

    results = agent._detect_large_class([cls])

    assert len(results) == 1
    assert results[0].smell_type == "large_class"
    assert results[0].severity == "medium"
    assert results[0].evidence["loc"] == 350


def test_large_class_not_detected_at_300_loc():
    agent = _make_agent()
    cls = _make_ucg_node("CLASS", "OkClass", line_start=1, line_end=300)

    results = agent._detect_large_class([cls])
    assert len(results) == 0


def test_large_class_not_detected_below_threshold():
    agent = _make_agent()
    cls = _make_ucg_node("CLASS", "SmallClass", line_start=1, line_end=50)

    results = agent._detect_large_class([cls])
    assert len(results) == 0


# ---------------------------------------------------------------------------
# Long method detector
# ---------------------------------------------------------------------------


def test_long_method_detected_above_50_loc():
    agent = _make_agent()
    fn = _make_ucg_node("METHOD", "processOrder", line_start=1, line_end=80)

    results = agent._detect_long_method([fn])

    assert len(results) == 1
    assert results[0].smell_type == "long_method"
    assert results[0].evidence["loc"] == 80


def test_long_method_not_detected_at_50_loc():
    agent = _make_agent()
    fn = _make_ucg_node("METHOD", "shortMethod", line_start=1, line_end=50)

    results = agent._detect_long_method([fn])
    assert len(results) == 0


# ---------------------------------------------------------------------------
# JDBC direct usage detector
# ---------------------------------------------------------------------------


def test_jdbc_usage_detected_by_qualified_name():
    agent = _make_agent()
    node = _make_ucg_node("METHOD", "preparedStatement", properties={})
    node.qualified_name = "com.example.Dao.preparedStatement"

    results = agent._detect_jdbc_usage([node])

    assert len(results) == 1
    assert results[0].smell_type == "tight_coupling"
    assert results[0].severity == "high"


def test_jdbc_usage_detected_in_properties():
    agent = _make_agent()
    node = _make_ucg_node("CLASS", "DbHelper", properties={"body": "conn.prepareStatement(sql)"})

    results = agent._detect_jdbc_usage([node])

    assert len(results) == 1


def test_jdbc_not_detected_for_clean_node():
    agent = _make_agent()
    node = _make_ucg_node("CLASS", "CleanService", properties={"visibility": "public"})

    results = agent._detect_jdbc_usage([node])
    assert len(results) == 0


# ---------------------------------------------------------------------------
# Dead code detector
# ---------------------------------------------------------------------------


def test_dead_code_detected_for_private_no_callers():
    agent = _make_agent()
    node = _make_ucg_node("METHOD", "_unusedHelper", properties={"visibility": "private"})

    # No incoming edges
    incoming: dict = {}
    outgoing: dict = {}

    results = agent._detect_dead_code([node], incoming, outgoing)

    assert len(results) == 1
    assert results[0].smell_type == "dead_code"
    assert results[0].severity == "low"


def test_dead_code_not_detected_with_incoming_calls():
    agent = _make_agent()
    node = _make_ucg_node("METHOD", "_helper", properties={"visibility": "private"})
    caller = _make_ucg_node("METHOD", "caller")

    call_edge = _make_ucg_edge("CALLS", caller.id, node.id)
    incoming = {node.id: [call_edge]}

    results = agent._detect_dead_code([node], incoming, {})
    assert len(results) == 0


def test_dead_code_skips_magic_methods():
    agent = _make_agent()
    node = _make_ucg_node("METHOD", "__init__", properties={"visibility": "public"})
    node.qualified_name = "com.example.MyClass.__init__"

    results = agent._detect_dead_code([node], {}, {})
    assert len(results) == 0


def test_dead_code_skips_module_nodes():
    agent = _make_agent()
    module_node = _make_ucg_node("MODULE", "mymodule", properties={"visibility": "public"})

    results = agent._detect_dead_code([module_node], {}, {})
    assert len(results) == 0


# ---------------------------------------------------------------------------
# Anemic domain model detector
# ---------------------------------------------------------------------------


def test_anemic_domain_model_detected_when_mostly_accessors():
    """A class where >80% methods are getters/setters should be flagged."""
    agent = _make_agent()

    cls = _make_ucg_node("CLASS", "User")
    accessors = [
        _make_ucg_node("METHOD", f"User.{name}")
        for name in ["getName", "setName", "getEmail", "setEmail", "isActive"]
    ]
    # One non-accessor
    business_method = _make_ucg_node("METHOD", "User.doSomething")

    all_methods = accessors + [business_method]
    node_by_id = {cls.id: cls, **{m.id: m for m in all_methods}}
    outgoing = {
        cls.id: [_make_ucg_edge("CONTAINS", cls.id, m.id) for m in all_methods]
    }

    results = agent._detect_anemic_domain_model([cls], outgoing, node_by_id)

    assert len(results) == 1
    assert results[0].smell_type == "anemic_domain_model"


def test_anemic_domain_model_not_detected_below_threshold():
    """A class with 50% accessors should NOT be flagged."""
    agent = _make_agent()

    cls = _make_ucg_node("CLASS", "RichDomain")
    methods = [
        _make_ucg_node("METHOD", f"RichDomain.{name}")
        for name in ["getName", "processOrder", "calculateTotal", "validate"]
    ]
    node_by_id = {cls.id: cls, **{m.id: m for m in methods}}
    outgoing = {
        cls.id: [_make_ucg_edge("CONTAINS", cls.id, m.id) for m in methods]
    }

    results = agent._detect_anemic_domain_model([cls], outgoing, node_by_id)
    assert len(results) == 0


def test_anemic_domain_model_skips_classes_with_fewer_than_3_methods():
    agent = _make_agent()

    cls = _make_ucg_node("CLASS", "TinyClass")
    methods = [_make_ucg_node("METHOD", "TinyClass.get")]
    node_by_id = {cls.id: cls, **{m.id: m for m in methods}}
    outgoing = {
        cls.id: [_make_ucg_edge("CONTAINS", cls.id, m.id) for m in methods]
    }

    results = agent._detect_anemic_domain_model([cls], outgoing, node_by_id)
    assert len(results) == 0


# ---------------------------------------------------------------------------
# Feature envy detector
# ---------------------------------------------------------------------------


def test_feature_envy_detected_when_many_foreign_targets():
    """A method calling methods on >5 different classes should trigger feature envy."""
    agent = _make_agent()

    fn = _make_ucg_node("METHOD", "doEverything")

    # Build 6 target methods on 6 different classes
    targets = []
    for i in range(6):
        t = _make_ucg_node("METHOD", f"Class{i}.action")
        t.qualified_name = f"com.example.Class{i}.action"
        targets.append(t)

    node_by_id = {fn.id: fn, **{t.id: t for t in targets}}
    outgoing = {
        fn.id: [_make_ucg_edge("CALLS", fn.id, t.id) for t in targets]
    }

    results = agent._detect_feature_envy([fn], outgoing, node_by_id)
    assert len(results) == 1
    assert results[0].smell_type == "feature_envy"


def test_feature_envy_not_detected_when_few_targets():
    agent = _make_agent()
    fn = _make_ucg_node("METHOD", "fewCalls")
    targets = [_make_ucg_node("METHOD", f"Class{i}.act") for i in range(3)]
    for t in targets:
        t.qualified_name = f"com.example.Class{t.id.hex[:4]}.act"
    node_by_id = {fn.id: fn, **{t.id: t for t in targets}}
    outgoing = {fn.id: [_make_ucg_edge("CALLS", fn.id, t.id) for t in targets]}

    results = agent._detect_feature_envy([fn], outgoing, node_by_id)
    assert len(results) == 0


# ---------------------------------------------------------------------------
# Severity ordering
# ---------------------------------------------------------------------------


def test_severity_order_is_correct():
    """SEVERITY_ORDER must rank critical < high < medium < low (lower = higher prio)."""
    agent = _make_agent()
    order = agent.SEVERITY_ORDER
    assert order["critical"] < order["high"] < order["medium"] < order["low"]


# ---------------------------------------------------------------------------
# SmellResult dataclass
# ---------------------------------------------------------------------------


def test_smell_result_has_required_fields():
    node_id = uuid.uuid4()
    result = SmellResult(
        smell_type="god_class",
        severity="high",
        affected_node_ids=[node_id],
        description="Test description",
        evidence={"method_count": 12},
        confidence=0.85,
    )
    assert result.smell_type == "god_class"
    assert result.severity == "high"
    assert result.llm_rationale is None  # default
    assert result.confidence == 0.85


# ---------------------------------------------------------------------------
# Agent instantiation
# ---------------------------------------------------------------------------


def test_agent_instantiates():
    agent = SmellDetectorAgent()
    assert agent is not None
    assert agent.stage_name == "analyzing"
