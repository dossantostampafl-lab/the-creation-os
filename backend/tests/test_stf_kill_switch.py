from app.security_task_force.kill_switch import KillSwitch


def test_global_kill_switch_blocks_new_dispatch():
    switch = KillSwitch()
    assert switch.dispatch_allowed("m1")
    switch.kill_global()
    assert not switch.dispatch_allowed("m1")


def test_mission_kill_is_scoped():
    switch = KillSwitch()
    switch.kill_mission("m1")
    assert not switch.dispatch_allowed("m1")
    assert switch.dispatch_allowed("m2")


def test_kill_survives_a_restart_and_unreadable_state_fails_closed(tmp_path):
    path = tmp_path / "kill.json"
    KillSwitch(path).kill_mission("m1")
    assert not KillSwitch(path).dispatch_allowed("m1")
    path.write_text("not json")
    assert not KillSwitch(path).dispatch_allowed("m2")
