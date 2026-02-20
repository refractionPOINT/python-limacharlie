import pytest

from limacharlie.Query import LCQuery

def noop(self):
    pass


def test_lcquery_rendereTable_event_ordering():
    elem = [
        {
            "ts": 123456789,
            "routing": {
                "foo": "bar"
            },
            "event": {
                "type": "foo",
                "data": {
                    "foo": "bar"
                }
            }
        }
    ]

    LCQuery._getAllEvents = noop
    LCQuery._populateSchema = noop
    LCQuery._setPrompt = noop
    lcq = LCQuery(replay=None, format="table", outFile=None)
    result = lcq._renderTable(elem)
    assert "ts" in result
    assert "routing" in result
    assert "event" in result
    assert "123456789" in result
    assert "foo" in result
    assert "bar" in result


def test_lcquery_rendereTable_non_event():
    elem = [
        {
            "ts": 123456789,
            "field1": {
                "foo": "bar"
            },
            "field2": {
                "type": "foo",
                "data": {
                    "foo": "bar"
                }
            }
        }
    ]

    LCQuery._getAllEvents = noop
    LCQuery._populateSchema = noop
    LCQuery._setPrompt = noop
    lcq = LCQuery(replay=None, format="table", outFile=None)
    result = lcq._renderTable(elem)
    assert "123456789" in result
    assert "field1" in result
    assert "field2" in result
