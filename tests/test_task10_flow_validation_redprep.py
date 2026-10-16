"""Paket 10: sunucu akış doğrulamasının çevrimdışı kabul örnekleri."""

from __future__ import annotations

import pytest

from fusion_cli.appserver.image_flows import FlowError, validate_flow


def _flow(node_ids: list[str], edges: list[tuple[str, str]]) -> dict[str, object]:
    return {
        "ad": "Doğrulama örneği",
        "dugumler": [
            {"id": node_id, "tur": "uret", "x": 0, "y": 0, "adet": 1} for node_id in node_ids
        ],
        "baglantilar": [{"kaynak": source, "hedef": target} for source, target in edges],
    }


def test_task10_valid_disconnected_nodes_are_preserved() -> None:
    flow = validate_flow(_flow(["a", "b"], []))
    assert [node["id"] for node in flow["dugumler"]] == ["a", "b"]


def test_task10_duplicate_raw_node_ids_are_rejected() -> None:
    with pytest.raises(FlowError):
        validate_flow(_flow(["a", "a"], []))


def test_task10_disconnected_cycle_is_rejected() -> None:
    with pytest.raises(FlowError):
        validate_flow(_flow(["a", "b", "c"], [("b", "c"), ("c", "b")]))


@pytest.mark.parametrize("coordinate", [float("nan"), float("inf"), -float("inf")])
def test_task10_nonfinite_coordinate_is_rejected(coordinate: float) -> None:
    flow = _flow(["a"], [])
    flow["dugumler"] = [{"id": "a", "tur": "uret", "x": coordinate, "y": 0}]
    with pytest.raises(FlowError):
        validate_flow(flow)


@pytest.mark.parametrize("edges", [[("a", "a")], [("a", "b"), ("a", "b")]])
def test_task10_self_or_duplicate_edges_are_rejected(edges):
    with pytest.raises(FlowError):
        validate_flow(_flow(["a", "b"], edges))


def test_task10_long_node_id_is_rejected_without_truncation():
    with pytest.raises(FlowError):
        validate_flow(_flow(["a" * 81], []))


@pytest.mark.parametrize("node_type", [[], {}])
def test_task10_invalid_node_type_is_a_flow_error(node_type):
    flow = _flow(["a"], [])
    flow["dugumler"][0]["tur"] = node_type
    with pytest.raises(FlowError):
        validate_flow(flow)


@pytest.mark.parametrize("endpoint", [[], {}])
def test_task10_invalid_endpoint_is_a_flow_error(endpoint):
    flow = _flow(["a", "b"], [("a", "b")])
    flow["baglantilar"][0]["hedef"] = endpoint
    with pytest.raises(FlowError):
        validate_flow(flow)


@pytest.mark.parametrize("count", [0, 5, True, 1.5, "2"])
def test_task10_invalid_variation_count_is_not_silently_dropped(count):
    flow = _flow(["a"], [])
    flow["dugumler"][0]["adet"] = count
    with pytest.raises(FlowError):
        validate_flow(flow)


def test_task10_text_cannot_connect_to_image_only_output():
    flow = _flow(["a", "b"], [("a", "b")])
    flow["dugumler"][0]["tur"] = "metin"
    flow["dugumler"][1]["tur"] = "cikti"
    with pytest.raises(FlowError):
        validate_flow(flow)


def test_task10_two_same_kind_inputs_are_rejected():
    flow = _flow(["a", "b", "c"], [("a", "c"), ("b", "c")])
    flow["dugumler"][0]["tur"] = "metin"
    flow["dugumler"][1]["tur"] = "metin"
    with pytest.raises(FlowError):
        validate_flow(flow)
