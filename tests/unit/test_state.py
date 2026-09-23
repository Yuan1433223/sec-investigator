from kks_runtime.state.session import _merge_dict, _merge_nested_dict


def test_merge_dict_basic():
    a = {"logs": {"qps": 100}, "security": {"cc": "ok"}}
    b = {"logs": {"qps": 200}}
    result = _merge_dict(a, b)
    assert result == {"logs": {"qps": 200}, "security": {"cc": "ok"}}


def test_merge_dict_new_key():
    a = {"logs": {}}
    b = {"machine": {"ping": "ok"}}
    result = _merge_dict(a, b)
    assert "machine" in result
    assert result["logs"] == {}


def test_merge_dict_empty_a():
    result = _merge_dict({}, {"x": 1})
    assert result == {"x": 1}


def test_merge_dict_empty_b():
    result = _merge_dict({"x": 1}, {})
    assert result == {"x": 1}


def test_merge_dict_overwrite():
    result = _merge_dict({"k": "old"}, {"k": "new"})
    assert result["k"] == "new"


def test_merge_nested_dict_combines_worker_outputs_per_asset():
    a = {
        "GF:node_product:1.1.1.1": {
            "asset": {"asset_id": "GF:node_product:1.1.1.1"},
            "machine": {"summary": "infra"},
        }
    }
    b = {
        "GF:node_product:1.1.1.1": {
            "security": {"summary": "shield"},
        }
    }
    result = _merge_nested_dict(a, b)
    assert result["GF:node_product:1.1.1.1"]["machine"] == {"summary": "infra"}
    assert result["GF:node_product:1.1.1.1"]["security"] == {"summary": "shield"}


def test_merge_nested_dict_adds_new_asset():
    result = _merge_nested_dict(
        {"GF:node:1.1.1.1": {"machine": {"summary": "ok"}}},
        {"GF:product:2.2.2.2": {"security": {"summary": "protected"}}},
    )
    assert set(result) == {"GF:node:1.1.1.1", "GF:product:2.2.2.2"}
