import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.pid_controller import PIDGains
from lib.rid_pid_loop import RunProfile, ab_compare, write_ab_report
from lib.rid_pid_supervisor import RIDSupervisorConfig

profile = RunProfile(
    setpoint_c=350.0, duration_s=150.0, dt_s=0.5, disturb_at_s=70.0, disturb_delta_c=-30.0
)
gains = PIDGains(kp=4.0, ki=0.25, kd=1.0)
rid = RIDSupervisorConfig(
    overtemp_limit=420.0,
    temp_lo=0.0,
    temp_hi=600.0,
    gain_schedule_mode="boost_when_stable",
    rle_clamp_threshold=0.30,
    rle_clamp_max_duty=30.0,
)
report = ab_compare(profile=profile, gains=gains, rid_cfg=rid)
j, m = write_ab_report(report)
print(
    json.dumps(
        {
            "verdict": report["verdict"],
            "reason": report["reason"],
            "baseline": report["baseline"]["metrics"],
            "pilot": report["pilot"]["metrics"],
            "deltas": report["deltas_pilot_minus_baseline"],
            "json": str(j).replace("\\", "/"),
        },
        indent=2,
    )
)
