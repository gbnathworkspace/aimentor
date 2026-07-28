"""Unit tests for JSON extraction in the document_extractor module."""

import json

import pytest

from app.services.document_extractor import (
    extract_json,
    MAX_ARRAY_ELEMENTS,
    MAX_JSON_DEPTH,
)


# --- Fixtures ---


@pytest.fixture
def flat_json(tmp_path):
    """Create a simple flat JSON file."""
    json_path = tmp_path / "flat.json"
    data = {"name": "Alice", "age": 30, "city": "New York"}
    json_path.write_text(json.dumps(data), encoding="utf-8")
    return str(json_path)


@pytest.fixture
def nested_json(tmp_path):
    """Create a JSON file with nested objects."""
    json_path = tmp_path / "nested.json"
    data = {
        "user": {
            "name": "Alice",
            "address": {
                "street": "123 Main St",
                "city": "Springfield",
            },
        },
        "active": True,
    }
    json_path.write_text(json.dumps(data), encoding="utf-8")
    return str(json_path)


@pytest.fixture
def deeply_nested_json(tmp_path):
    """Create a JSON file nested exactly at the depth limit."""
    json_path = tmp_path / "deep.json"
    # Build nesting: 10 levels deep means depth 0 is root dict,
    # depth 1 is first child, ... depth 9 is the deepest allowed.
    # At depth 10 content should be ignored.
    data = {"level": "value_at_root"}
    current = data
    for i in range(1, 12):  # creates 11 more levels (total depth 12)
        child = {"level": f"value_at_{i}"}
        current["child"] = child
        current = child
    json_path.write_text(json.dumps(data), encoding="utf-8")
    return str(json_path)


@pytest.fixture
def array_json(tmp_path):
    """Create a JSON file with arrays."""
    json_path = tmp_path / "array.json"
    data = {"items": [1, 2, 3, 4, 5], "tags": ["python", "testing"]}
    json_path.write_text(json.dumps(data), encoding="utf-8")
    return str(json_path)


@pytest.fixture
def large_array_json(tmp_path):
    """Create a JSON file with an array exceeding 100 elements."""
    json_path = tmp_path / "large_array.json"
    data = {"numbers": list(range(200))}
    json_path.write_text(json.dumps(data), encoding="utf-8")
    return str(json_path)


@pytest.fixture
def mixed_json(tmp_path):
    """Create a JSON file with mixed arrays and objects."""
    json_path = tmp_path / "mixed.json"
    data = {
        "users": [
            {"name": "Alice", "scores": [95, 88]},
            {"name": "Bob", "scores": [72, 91]},
        ],
        "metadata": {"count": 2, "source": "test"},
    }
    json_path.write_text(json.dumps(data), encoding="utf-8")
    return str(json_path)


@pytest.fixture
def malformed_json(tmp_path):
    """Create a malformed JSON file."""
    json_path = tmp_path / "malformed.json"
    json_path.write_text("{invalid json: [}", encoding="utf-8")
    return str(json_path)


@pytest.fixture
def empty_json_file(tmp_path):
    """Create an empty JSON file (no content at all)."""
    json_path = tmp_path / "empty.json"
    json_path.write_text("", encoding="utf-8")
    return str(json_path)


@pytest.fixture
def empty_object_json(tmp_path):
    """Create a JSON file with an empty object."""
    json_path = tmp_path / "empty_object.json"
    json_path.write_text("{}", encoding="utf-8")
    return str(json_path)


@pytest.fixture
def empty_array_json(tmp_path):
    """Create a JSON file with an empty array."""
    json_path = tmp_path / "empty_array.json"
    json_path.write_text("[]", encoding="utf-8")
    return str(json_path)


# --- Tests ---


@pytest.mark.asyncio
async def test_extract_json_flat(flat_json):
    """Test extraction of a simple flat JSON object."""
    result = await extract_json(flat_json)
    lines = result.split("\n")

    assert "root.name: Alice" in lines
    assert "root.age: 30" in lines
    assert "root.city: New York" in lines
    assert len(lines) == 3


@pytest.mark.asyncio
async def test_extract_json_nested(nested_json):
    """Test extraction of nested JSON objects with dot-path notation."""
    result = await extract_json(nested_json)
    lines = result.split("\n")

    assert "root.user.name: Alice" in lines
    assert "root.user.address.street: 123 Main St" in lines
    assert "root.user.address.city: Springfield" in lines
    assert "root.active: True" in lines


@pytest.mark.asyncio
async def test_extract_json_depth_limit(deeply_nested_json):
    """Test that traversal stops at depth 10, ignoring deeper content."""
    result = await extract_json(deeply_nested_json)

    # Build expected paths up to depth 9 (10 levels: root at 0, then 9 nested)
    # root is at depth 0, root.child at depth 1, root.child.child at depth 2, etc.
    # The function starts with depth=0 for the root object.
    # Root object keys (level, child) are at depth 1.
    # root.child.level, root.child.child are at depth 2.
    # So we should see content up to depth 9 but NOT at depth 10.
    lines = result.split("\n")

    # The root level value should be present
    assert "root.level: value_at_root" in lines

    # Content at depth 10 and beyond should NOT appear
    # Build the path that would be at depth 10
    deep_path = "root" + ".child" * 10 + ".level"
    assert deep_path not in result


@pytest.mark.asyncio
async def test_extract_json_arrays(array_json):
    """Test extraction of arrays with index notation."""
    result = await extract_json(array_json)
    lines = result.split("\n")

    assert "root.items[0]: 1" in lines
    assert "root.items[1]: 2" in lines
    assert "root.items[4]: 5" in lines
    assert "root.tags[0]: python" in lines
    assert "root.tags[1]: testing" in lines


@pytest.mark.asyncio
async def test_extract_json_array_truncation(large_array_json):
    """Test that arrays are truncated to first 100 elements."""
    result = await extract_json(large_array_json)
    lines = result.split("\n")

    # Should have exactly 100 lines (one per element)
    assert len(lines) == MAX_ARRAY_ELEMENTS

    # First and last allowed elements should be present
    assert "root.numbers[0]: 0" in lines
    assert "root.numbers[99]: 99" in lines

    # Element 100 and beyond should NOT be present
    assert "root.numbers[100]" not in result
    assert "root.numbers[199]" not in result


@pytest.mark.asyncio
async def test_extract_json_mixed_arrays_and_objects(mixed_json):
    """Test extraction of JSON with mixed arrays and nested objects."""
    result = await extract_json(mixed_json)
    lines = result.split("\n")

    assert "root.users[0].name: Alice" in lines
    assert "root.users[0].scores[0]: 95" in lines
    assert "root.users[0].scores[1]: 88" in lines
    assert "root.users[1].name: Bob" in lines
    assert "root.users[1].scores[0]: 72" in lines
    assert "root.users[1].scores[1]: 91" in lines
    assert "root.metadata.count: 2" in lines
    assert "root.metadata.source: test" in lines


@pytest.mark.asyncio
async def test_extract_json_malformed(malformed_json):
    """Test that malformed JSON raises ValueError."""
    with pytest.raises(ValueError, match="Malformed JSON"):
        await extract_json(malformed_json)


@pytest.mark.asyncio
async def test_extract_json_empty_file(empty_json_file):
    """Test that an empty file raises ValueError."""
    with pytest.raises(ValueError):
        await extract_json(empty_json_file)


@pytest.mark.asyncio
async def test_extract_json_empty_object(empty_object_json):
    """Test extraction of an empty JSON object."""
    result = await extract_json(empty_object_json)
    assert result == "root: {}"


@pytest.mark.asyncio
async def test_extract_json_empty_array(empty_array_json):
    """Test extraction of a JSON file containing an empty array."""
    result = await extract_json(empty_array_json)
    assert result == "root: []"


@pytest.mark.asyncio
async def test_extract_json_nonexistent_file():
    """Test non-existent file raises ValueError."""
    with pytest.raises(ValueError):
        await extract_json("/nonexistent/path/to/file.json")


@pytest.mark.asyncio
async def test_extract_json_null_values(tmp_path):
    """Test extraction of JSON with null values."""
    json_path = tmp_path / "nulls.json"
    data = {"name": "Test", "value": None, "active": False}
    json_path.write_text(json.dumps(data), encoding="utf-8")

    result = await extract_json(str(json_path))
    lines = result.split("\n")

    assert "root.name: Test" in lines
    assert "root.value: None" in lines
    assert "root.active: False" in lines


@pytest.mark.asyncio
async def test_extract_json_nested_empty_objects(tmp_path):
    """Test extraction of nested empty objects and arrays."""
    json_path = tmp_path / "nested_empty.json"
    data = {"empty_obj": {}, "empty_arr": [], "data": "value"}
    json_path.write_text(json.dumps(data), encoding="utf-8")

    result = await extract_json(str(json_path))
    lines = result.split("\n")

    assert "root.empty_obj: {}" in lines
    assert "root.empty_arr: []" in lines
    assert "root.data: value" in lines


@pytest.mark.asyncio
async def test_extract_json_depth_boundary(tmp_path):
    """Test content at exactly depth 9 is included but depth 10 is excluded."""
    json_path = tmp_path / "boundary.json"
    # Build a chain of exactly 9 nested objects from root
    # root (depth 0) -> a (depth 1) -> b (depth 2) -> ... -> i (depth 9) -> j (depth 10)
    data: dict = {}
    current = data
    keys = "abcdefghij"  # 10 keys = depths 1 through 10
    for key in keys:
        current[key] = {}
        current = current[key]
    current["leaf"] = "should_not_appear"  # This would be depth 11

    # Add a value at depth 9 (key 'i' creates the dict at depth 9)
    # Let's add explicit leaf values at each level
    data["val"] = "depth1"
    data["a"]["val"] = "depth2"
    data["a"]["b"]["val"] = "depth3"
    data["a"]["b"]["c"]["val"] = "depth4"
    data["a"]["b"]["c"]["d"]["val"] = "depth5"
    data["a"]["b"]["c"]["d"]["e"]["val"] = "depth6"
    data["a"]["b"]["c"]["d"]["e"]["f"]["val"] = "depth7"
    data["a"]["b"]["c"]["d"]["e"]["f"]["g"]["val"] = "depth8"
    data["a"]["b"]["c"]["d"]["e"]["f"]["g"]["h"]["val"] = "depth9"
    data["a"]["b"]["c"]["d"]["e"]["f"]["g"]["h"]["i"]["val"] = "depth10"

    json_path.write_text(json.dumps(data), encoding="utf-8")

    result = await extract_json(str(json_path))

    # depth1 through depth9 should be present (depths 1-9 from root at 0)
    assert "root.val: depth1" in result
    assert "root.a.val: depth2" in result
    assert "root.a.b.val: depth3" in result
    assert "root.a.b.c.val: depth4" in result
    assert "root.a.b.c.d.val: depth5" in result
    assert "root.a.b.c.d.e.val: depth6" in result
    assert "root.a.b.c.d.e.f.val: depth7" in result
    assert "root.a.b.c.d.e.f.g.val: depth8" in result
    assert "root.a.b.c.d.e.f.g.h.val: depth9" in result

    # depth10 should NOT be present (would be at depth 10 from root)
    assert "depth10" not in result
    assert "should_not_appear" not in result
