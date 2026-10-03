import unittest

from lola_environment_fabric import (
    EnvironmentClass,
    EnvironmentRequest,
    MountSpec,
    NetworkMode,
    ResourceBudget,
    environment_360,
    environment_7d,
    plan_environment,
    validate_entitlement,
)


class EnvironmentFabricTests(unittest.TestCase):
    def test_non_execution_routes_to_none(self):
        manifest = plan_environment(EnvironmentRequest(task_id="t0", workload="chat", needs_execution=False))
        self.assertEqual(manifest.environment_class, EnvironmentClass.NONE)
        self.assertEqual(manifest.network_mode, NetworkMode.OFF)
        self.assertFalse(manifest.execution_authority)

    def test_small_deterministic_work_routes_to_micro(self):
        manifest = plan_environment(EnvironmentRequest(task_id="t1", workload="hash"))
        self.assertEqual(manifest.environment_class, EnvironmentClass.MICRO)

    def test_build_routes_to_build_environment(self):
        manifest = plan_environment(
            EnvironmentRequest(task_id="t2", workload="android", needs_build=True, toolchains=("jdk", "gradle"))
        )
        self.assertEqual(manifest.environment_class, EnvironmentClass.BUILD)
        self.assertEqual(manifest.toolchains, ("jdk", "gradle"))

    def test_untrusted_input_forces_isolation_and_network_off(self):
        manifest = plan_environment(
            EnvironmentRequest(
                task_id="t3",
                workload="skill-quarantine",
                untrusted_input=True,
                needs_network=True,
                allowed_hosts=("example.invalid",),
            )
        )
        self.assertEqual(manifest.environment_class, EnvironmentClass.ISOLATED)
        self.assertEqual(manifest.network_mode, NetworkMode.OFF)
        self.assertEqual(manifest.allowed_hosts, ())

    def test_network_is_allowlist_only(self):
        manifest = plan_environment(
            EnvironmentRequest(
                task_id="t4",
                workload="python",
                needs_network=True,
                allowed_hosts=("pypi.org", "pypi.org"),
            )
        )
        self.assertEqual(manifest.network_mode, NetworkMode.RESTRICTED)
        self.assertEqual(manifest.allowed_hosts, ("pypi.org",))

    def test_restricted_network_without_hosts_is_rejected(self):
        with self.assertRaises(ValueError):
            plan_environment(EnvironmentRequest(task_id="t5", workload="python", needs_network=True))

    def test_write_mount_requires_explicit_entitlement(self):
        manifest = plan_environment(
            EnvironmentRequest(
                task_id="t6",
                workload="python",
                mounts=(MountSpec("/workspace/project", "READ_WRITE"),),
            )
        )
        allowed, missing = validate_entitlement(manifest, authorized_capabilities=("environment.execute",))
        self.assertFalse(allowed)
        self.assertEqual(missing, ("workspace.write",))

        allowed, missing = validate_entitlement(
            manifest,
            authorized_capabilities=("environment.execute", "workspace.write"),
        )
        self.assertTrue(allowed)
        self.assertEqual(missing, ())

    def test_network_requires_separate_entitlement(self):
        manifest = plan_environment(
            EnvironmentRequest(
                task_id="t7",
                workload="python",
                needs_network=True,
                allowed_hosts=("pypi.org",),
            )
        )
        allowed, missing = validate_entitlement(manifest, authorized_capabilities=("environment.execute",))
        self.assertFalse(allowed)
        self.assertEqual(missing, ("network.restricted",))

    def test_resource_budget_rejects_invalid_limits(self):
        with self.assertRaises(ValueError):
            plan_environment(
                EnvironmentRequest(task_id="t8", workload="python", budget=ResourceBudget(ram_mb=-1))
            )

    def test_360_and_7d_are_deterministic_projections(self):
        manifest = plan_environment(
            EnvironmentRequest(
                task_id="t9",
                workload="analysis",
                needs_analysis=True,
                mounts=(MountSpec("/reference", "READ_ONLY"),),
                budget=ResourceBudget(ram_mb=512, cpu_units=2, wall_time_s=90),
            )
        )
        view360 = environment_360(manifest)
        view7d = environment_7d(manifest)
        self.assertEqual(view360["structure"], "ANALYSIS")
        self.assertEqual(view360["runtime"]["ram_mb"], 512)
        self.assertEqual(view7d["behavior"], "DISPOSABLE_WORKER")
        self.assertEqual(view7d["security_trust"]["credentials"], "OUTSIDE_WORKER")


if __name__ == "__main__":
    unittest.main()
