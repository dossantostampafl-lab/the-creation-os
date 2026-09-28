import json
import logging

from app.security_task_force.telemetry import emit


def test_emit_writes_one_json_line_with_correlation_ids_and_redacts_secrets(caplog):
    with caplog.at_level(logging.INFO, logger="stf"):
        record = emit("action.decided", mission_id="m1", action_id="a1", environment_id="cyber_range:lab-a",
                      decision="permit", token="s3cret", nested={"password": "hunter2"})
    line = json.loads(caplog.records[-1].getMessage())
    assert line == record
    assert (line["event"], line["mission_id"], line["environment_id"]) == ("action.decided", "m1", "cyber_range:lab-a")
    assert line["token"] == "[redacted]" and line["nested"]["password"] == "[redacted]"
    assert "s3cret" not in caplog.text and "hunter2" not in caplog.text


def test_the_worker_configures_logging_so_telemetry_is_not_dropped():
    import inspect

    from app.security_task_force import temporal_worker

    assert "logging.basicConfig" in inspect.getsource(temporal_worker.main)
