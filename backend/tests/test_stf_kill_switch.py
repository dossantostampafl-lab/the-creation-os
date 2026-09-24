from app.security_task_force.kill_switch import KillSwitch


def test_global_kill_switch_blocks_new_dispatch():
    switch=KillSwitch()
    assert switch.dispatch_allowed("m1")
    switch.kill_global()
    assert not switch.dispatch_allowed("m1")


def test_mission_kill_is_scoped():
    switch=KillSwitch()
    switch.kill_mission("m1")
    assert not switch.dispatch_allowed("m1")
    assert switch.dispatch_allowed("m2")
