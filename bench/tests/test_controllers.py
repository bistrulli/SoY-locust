"""Unit tests for the scaling controllers (stdlib unittest)."""
import unittest

from bench.controllers import (
    ControlContext, HPAController, ManualFixed, ManualSchedule,
    NoneController, OpenClassController, make_controller,
)


def ctx(**kw):
    return ControlContext(**kw)


class TestHPA(unittest.TestCase):
    def test_scale_up(self):
        hpa = HPAController(target_utilization=0.5, min_replicas=1, max_replicas=16)
        d = hpa.decide(ctx(current_replicas=2, cpu_util_per_replica=0.9, elapsed_s=0))
        self.assertEqual(d, 4)  # ceil(2 * 0.9/0.5) = 4

    def test_within_tolerance_no_change(self):
        hpa = HPAController(target_utilization=0.5, tolerance=0.10, max_replicas=16)
        d = hpa.decide(ctx(current_replicas=3, cpu_util_per_replica=0.52, elapsed_s=0))
        self.assertEqual(d, 3)  # ratio 1.04 within tolerance

    def test_bounds(self):
        hpa = HPAController(target_utilization=0.5, min_replicas=2, max_replicas=6)
        self.assertEqual(
            hpa.decide(ctx(current_replicas=5, cpu_util_per_replica=5.0, elapsed_s=0)), 6)
        hpa2 = HPAController(target_utilization=0.5, min_replicas=2, max_replicas=6)
        self.assertEqual(
            hpa2.decide(ctx(current_replicas=5, cpu_util_per_replica=0.0, elapsed_s=0)), 2)

    def test_downscale_stabilization(self):
        hpa = HPAController(target_utilization=0.5, min_replicas=1, max_replicas=8,
                            downscale_stabilization_s=60.0)
        # t=0 strong rise -> 8
        self.assertEqual(
            hpa.decide(ctx(current_replicas=4, cpu_util_per_replica=0.9, elapsed_s=0)), 8)
        # t=5 zero load -> would stay high (max over the downscale window)
        self.assertEqual(
            hpa.decide(ctx(current_replicas=8, cpu_util_per_replica=0.1, elapsed_s=5)), 8)
        # t=70 window elapsed -> scales down
        self.assertEqual(
            hpa.decide(ctx(current_replicas=8, cpu_util_per_replica=0.1, elapsed_s=70)), 2)


class TestManual(unittest.TestCase):
    def test_fixed(self):
        self.assertEqual(ManualFixed(4, max_replicas=8).decide(ctx()), 4)
        self.assertEqual(ManualFixed(4, max_replicas=3).decide(ctx()), 3)  # clamp to max

    def test_schedule_step(self):
        m = ManualSchedule([(0, 1), (10, 3), (20, 2)], max_replicas=8)
        self.assertEqual(m.decide(ctx(elapsed_s=5)), 1)
        self.assertEqual(m.decide(ctx(elapsed_s=10)), 3)
        self.assertEqual(m.decide(ctx(elapsed_s=15)), 3)
        self.assertEqual(m.decide(ctx(elapsed_s=25)), 2)


class TestOpenClassAndUopt(unittest.TestCase):
    def test_openclass_formula(self):
        c = OpenClassController(target_utilization=0.2, min_replicas=1, max_replicas=32)
        # ceil(100 * 0.038 / 0.2) = ceil(19) = 19
        d = c.decide(ctx(arrival_rate=100, service_time=0.038, max_replicas=32))
        self.assertEqual(d, 19)

    def test_uopt_fallback_or_opt(self):
        # uopt must return a bounded integer, whether or not OPTCTRL is present
        c = make_controller("uopt", target_utilization=0.2, min_replicas=1, max_replicas=16)
        d = c.decide(ctx(arrival_rate=50, service_time=0.04, active_users=80,
                         max_replicas=16))
        self.assertTrue(1 <= d <= 16)
        self.assertIsInstance(d, int)


class TestFactory(unittest.TestCase):
    def test_dispatch(self):
        self.assertIsInstance(make_controller("none"), NoneController)
        self.assertIsInstance(make_controller("hpa"), HPAController)
        self.assertIsInstance(make_controller("manual", fixed_replicas=2), ManualFixed)
        self.assertIsInstance(
            make_controller("manual-sched", schedule=[(0, 1)]), ManualSchedule)
        with self.assertRaises(ValueError):
            make_controller("bogus")


if __name__ == "__main__":
    unittest.main()
