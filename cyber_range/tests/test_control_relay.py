from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('relay', Path(__file__).parents[1] / 'control_relay.py')
relay = importlib.util.module_from_spec(spec)
spec.loader.exec_module(relay)


def test_relay_rejects_public_binding_and_missing_secret():
    for bind, token in [('0.0.0.0','x'*32),('8.8.8.8','x'*32),('127.0.0.1','')]:
        with pytest.raises(ValueError):
            relay.serve(bind,0,token)


def test_relay_allows_only_declared_lifecycle_routes():
    assert relay.allowed('GET','/state')
    assert relay.allowed('POST','/scenarios/juice-shop-baseline/start')
    assert relay.allowed('GET','/campaigns')
    assert relay.allowed('GET','/campaigns/stf-foundation-v1/state')
    assert relay.allowed('POST','/campaigns/stf-foundation-v1/start')
    assert relay.allowed('POST','/campaigns/stf-foundation-v1/advance')
    assert not relay.allowed('POST','/scenarios/../../etc/start')
    assert not relay.allowed('GET','http://remote.example/state')
    assert not relay.allowed('GET','/state?target=remote')
    assert not relay.allowed('POST','/evidence')
