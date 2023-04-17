import pytest
import configparser
from gpiozero import Device
from gpiozero.pins.mock import MockFactory
from smartmeter.aux import LoadManager, Load
from time import monotonic

Device.pin_factory = MockFactory()


@pytest.mark.parametrize("result", [True, False])
def test_load_status(result):
    """
    Test if we can get the status of the load: 1 if the load is on, 0 if the load is off.
    Also test if we can get the is_on and is_off values.
    """
    load = Load(
        name="test load", max_power=2300, switch_on=2300, hold_timer=10
    )

    load.on() if result is True else load.off
    assert load.status == ("ON" if result else "OFF")
    assert load.is_on == result
    assert load.is_off is not result


def test_loadmanager_add_load():
    """
    Test the loadmanager.
    """
    load_cfg = configparser.ConfigParser()
    load_cfg["load:aux"] = {
        "enabled": True,
        "max_power": "2300",
        "switch_on": "75",
        "switch_off": "10",
        "hold_timer": "10",
    }

    lm = LoadManager()
    lm.add_load(load_cfg["load:aux"])

    assert len(lm.load_list) == 1


def test_loadmanager_process():
    """
    Testing the loadmanager processing the data received from the digital meter.
    """
    load_cfg = configparser.ConfigParser()
    load_cfg["load:aux"] = {
        "enabled": True,
        "max_power": "2300",  # watt
        "switch_on": "1725",  # watt
        "switch_off": "230",  # watt
        "hold_timer": "5",  # seconds
    }

    lm = LoadManager()
    lm.add_load(load_cfg["load:aux"])

    lm.process(
        {"actual_total_injection": 0, "actual_total_consumption": 120}
    )


@pytest.mark.parametrize(
    "injected,consumed,state_time,begin_state,end_state",
    [
        pytest.param(0, 0, 0, False, False, id="No power, load is off, holdtimer not expired."),
        pytest.param(0, 0, 10, False, False, id="No power, load is off, holdtimer expired."),
        pytest.param(2000, 0, 0, False, False, id="2000W injected, load is off, holdtimer not expired."),
        pytest.param(2000, 0, 10, False, False, id="2000W injected, load is off, holdtimer expired."),
        pytest.param(2300, 0, 0, False, False, id="2300W injected, load is off, holdtimer not expired."),
        pytest.param(2300, 0, 10, False, True, id="2300W injected, load is off, holdtimer expired."),
        pytest.param(0, 0, 0, True, True, id="No power, load is on, holdtimer not expired."),
        pytest.param(0, 0, 10, True, True, id="No power, load is on, holdtimer expired."),
        pytest.param(0, 150, 0, False, False, id="150 watt consumed, load is off, holdtimer not expired."),
        pytest.param(0, 150, 10, False, False, id="150 watt consumed, load is off, holdtimer expired."),
        pytest.param(0, 150, 0, True, True, id="150 watt consumed, load is on, holdtimer not expired."),
        pytest.param(0, 150, 10, True, False, id="150 watt consumed, load is on, holdtimer expired."),
    ],
)
def test_load(consumed, injected, state_time, begin_state, end_state):
    """
    Test one load.
    """
    load = Load(
        name="test_load", max_power=2300, switch_on=1725, hold_timer=5
    )

    load.on() if begin_state else load.off()
    load.state_start_time = monotonic() - state_time

    result = load.process(injected, consumed)
    assert result == end_state
