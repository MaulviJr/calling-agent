import pytest
from legacy.app.voice.pacing import PcmPacer


def test_send_overhead_is_included_in_frame_duration():
    now = [0.0]
    pacer = PcmPacer(clock=lambda: now[0])
    for _ in range(100):
        pacer.begin_frame(640)
        now[0] += .005  # Five milliseconds to enqueue/send.
        assert pacer.remaining() == pytest.approx(.015)
        now[0] += pacer.remaining()
    assert now[0] == pytest.approx(2.0)  # Not 2.5 seconds for two seconds of PCM.


def test_provider_stall_does_not_cause_catchup_burst():
    now = [0.0]
    pacer = PcmPacer(clock=lambda: now[0])
    pacer.begin_frame(640)
    now[0] = 1.0
    pacer.begin_frame(640)
    assert pacer.remaining() == pytest.approx(.02)


def test_late_timer_wakeups_do_not_accumulate_drift():
    now = [0.0]
    pacer = PcmPacer(clock=lambda: now[0])
    for _ in range(100):
        pacer.begin_frame(640)
        now[0] += .002
        now[0] += pacer.remaining() + .004
    assert now[0] == pytest.approx(2.004)
