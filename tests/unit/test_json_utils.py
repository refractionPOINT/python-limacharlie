import json

from limacharlie import json_utils  # your module that wraps orjson

def test_dumps_no_indent_no_sort():
    obj = {"b": 1, "a": 2}
    # Our function output (compact form)
    our_output = json_utils.dumps(obj)
    # Standard json.dumps output with compact separators
    std_output = json.dumps(obj, separators=(',', ':'))
    assert our_output == std_output

def test_dumps_with_indent_and_sort_keys():
    obj = {"b": 1, "a": 2}
    # When indent is provided, our function uses orjson.OPT_INDENT_2,
    # and sort_keys sorts the output.
    our_output = json_utils.dumps(obj, indent=2, sort_keys=True)
    std_output = json.dumps(obj, indent=2, sort_keys=True)
    # Compare line by line to avoid differences in trailing whitespace.
    our_lines = our_output.strip().splitlines()
    std_lines = std_output.strip().splitlines()
    assert our_lines == std_lines

def test_loads_with_str_and_bytes():
    obj = {"a": 1, "b": 2}
    json_str = json.dumps(obj, separators=(',', ':'))
    
    # Test loads with a string input.
    loaded_obj_str = json_utils.loads(json_str)
    assert loaded_obj_str == obj
    
    # Test loads with bytes input.
    json_bytes = json_str.encode('utf-8')
    loaded_obj_bytes = json_utils.loads(json_bytes)
    assert loaded_obj_bytes == obj

def test_dump_and_load(tmp_path):
    obj = {"a": 1, "b": 2}
    # Create a temporary file path using the pytest tmp_path fixture.
    file_path = tmp_path / "test.json"
    
    # Write using dump.
    with file_path.open('w', encoding='utf-8') as f:
        json_utils.dump(obj, f)
    
    # Read back using load.
    with file_path.open('r', encoding='utf-8') as f:
        loaded_obj = json_utils.load(f)
    
    assert loaded_obj == obj