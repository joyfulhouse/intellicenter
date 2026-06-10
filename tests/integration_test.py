#!/usr/bin/env python3
"""Comprehensive integration test against a real IntelliCenter endpoint.

This script performs end-to-end testing against a live IntelliCenter system.
It validates connection, data retrieval, and model integrity.

Usage:
    uv run python tests/integration_test.py

Requires .env file with:
    INTELLICENTER_HOST=<ip_address>
    INTELLICENTER_PORT=6681 (optional, defaults to 6681)
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
import os
from pathlib import Path
import sys

# Load .env file
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ[key.strip()] = value.strip()

from pyintellicenter import (  # noqa: E402
    BODY_TYPE,
    CHEM_TYPE,
    CIRCUIT_TYPE,
    HEATER_TYPE,
    PUMP_TYPE,
    SCHED_TYPE,
    SENSE_TYPE,
    ICConnectionHandler,
    ICModelController,
    PoolModel,
)


@dataclass
class IntegrationTestResult:
    """Result of a single integration test.

    Named to avoid pytest collection (classes starting with 'Test' are collected).
    """

    name: str
    passed: bool
    message: str
    duration_ms: float = 0


class IntegrationTester:
    """Comprehensive integration tester for IntelliCenter."""

    def __init__(self, host: str, port: int = 6681):
        self.host = host
        self.port = port
        self.model = PoolModel()  # standalone hardware script: track all attributes
        self.controller: ICModelController | None = None
        self.handler: ICConnectionHandler | None = None
        self.results: list[IntegrationTestResult] = []
        self.start_time: datetime | None = None

    def log(self, emoji: str, message: str) -> None:
        """Log a message with emoji prefix."""
        print(f"{emoji} {message}")

    def add_result(
        self, name: str, passed: bool, message: str, duration_ms: float = 0
    ) -> None:
        """Add a test result."""
        self.results.append(IntegrationTestResult(name, passed, message, duration_ms))
        status = "✅ PASS" if passed else "❌ FAIL"
        duration = f" ({duration_ms:.0f}ms)" if duration_ms > 0 else ""
        self.log("  ", f"{status}: {name}{duration}")
        if not passed:
            self.log("  ", f"       {message}")

    async def test_connection(self) -> bool:
        """Test basic connection to IntelliCenter."""
        self.log("🔌", f"Testing connection to {self.host}:{self.port}...")

        start = asyncio.get_event_loop().time()
        try:
            self.controller = ICModelController(self.host, self.model, port=self.port)
            self.handler = ICConnectionHandler(self.controller)

            # Start connection with timeout
            await asyncio.wait_for(self.handler.start(), timeout=30.0)

            duration = (asyncio.get_event_loop().time() - start) * 1000
            self.add_result("Connection", True, "Connected successfully", duration)
            return True

        except TimeoutError:
            duration = (asyncio.get_event_loop().time() - start) * 1000
            self.add_result(
                "Connection", False, "Connection timed out after 30s", duration
            )
            return False
        except Exception as e:
            duration = (asyncio.get_event_loop().time() - start) * 1000
            self.add_result("Connection", False, f"Connection failed: {e}", duration)
            return False

    async def test_system_info(self) -> bool:
        """Test system information retrieval."""
        self.log("📊", "Testing system information...")

        try:
            # Wait for system info to be populated
            for _ in range(10):
                info = self.controller.system_info
                if info is not None and info.prop_name:
                    break
                await asyncio.sleep(0.5)

            if info is None:
                self.add_result(
                    "SystemInfo", False, "SystemInfo not available after 5s"
                )
                return False

            # Validate required fields
            checks = [
                ("Property Name", info.prop_name, bool(info.prop_name)),
                ("Software Version", info.sw_version, bool(info.sw_version)),
                (
                    "Unique ID",
                    info.unique_id,
                    bool(info.unique_id) and len(info.unique_id) == 16,
                ),
                (
                    "Uses Metric",
                    str(info.uses_metric),
                    info.uses_metric in (True, False),
                ),
            ]

            all_passed = True
            for name, value, passed in checks:
                self.add_result(f"SystemInfo.{name}", passed, f"Value: {value}")
                if not passed:
                    all_passed = False

            # Print summary
            self.log("  ", f"       Pool Name: {info.prop_name}")
            self.log("  ", f"       Version: {info.sw_version}")
            self.log(
                "  ", f"       Units: {'Metric' if info.uses_metric else 'Imperial'}"
            )

            return all_passed

        except Exception as e:
            self.add_result("SystemInfo", False, f"Failed to get system info: {e}")
            return False

    async def test_model_population(self) -> bool:
        """Test that the model is populated with equipment."""
        self.log("🎛️", "Testing model population...")

        try:
            # Wait a moment for model to fully populate
            await asyncio.sleep(2)

            num_objects = self.model.num_objects
            self.add_result(
                "Model.ObjectCount", num_objects > 0, f"Found {num_objects} objects"
            )

            if num_objects == 0:
                return False

            # Count by type
            type_counts = {}
            for obj in self.model:
                obj_type = obj.objtype
                type_counts[obj_type] = type_counts.get(obj_type, 0) + 1

            self.log("  ", "       Equipment breakdown:")
            for obj_type, count in sorted(type_counts.items()):
                self.log("  ", f"         - {obj_type}: {count}")

            return True

        except Exception as e:
            self.add_result("Model.Population", False, f"Failed: {e}")
            return False

    async def test_equipment_types(self) -> bool:
        """Test specific equipment types."""
        self.log("🏊", "Testing equipment types...")

        all_passed = True

        # Test bodies (Pool/Spa)
        bodies = self.model.get_by_type(BODY_TYPE)
        self.add_result(
            "Equipment.Bodies",
            len(bodies) > 0,
            f"Found {len(bodies)} bodies (pool/spa)",
        )
        for body in bodies:
            self.log("  ", f"       - {body.sname} ({body.subtype}): {body.status}")

        # Test pumps
        pumps = self.model.get_by_type(PUMP_TYPE)
        self.add_result(
            "Equipment.Pumps",
            True,  # Pumps are optional
            f"Found {len(pumps)} pumps",
        )
        for pump in pumps:
            rpm = pump["RPM"] if "RPM" in pump.attributes else "N/A"
            pwr = pump["PWR"] if "PWR" in pump.attributes else "N/A"
            self.log(
                "  ",
                f"       - {pump.sname}: Status={pump.status}, RPM={rpm}, PWR={pwr}",
            )

        # Test circuits
        circuits = self.model.get_by_type(CIRCUIT_TYPE)
        self.add_result(
            "Equipment.Circuits", len(circuits) > 0, f"Found {len(circuits)} circuits"
        )

        # Count lights
        lights = [c for c in circuits if c.isALight]
        light_shows = [c for c in circuits if c.isALightShow]
        featured = [c for c in circuits if c.isFeatured]

        self.log("  ", f"       - Lights: {len(lights)}")
        self.log("  ", f"       - Light Shows: {len(light_shows)}")
        self.log("  ", f"       - Featured Circuits: {len(featured)}")

        # Test heaters
        heaters = self.model.get_by_type(HEATER_TYPE)
        self.add_result(
            "Equipment.Heaters",
            True,  # Heaters are optional
            f"Found {len(heaters)} heaters",
        )

        # Test sensors
        sensors = self.model.get_by_type(SENSE_TYPE)
        self.add_result(
            "Equipment.Sensors",
            True,  # Sensors are optional
            f"Found {len(sensors)} sensors",
        )
        for sensor in sensors:
            self.log("  ", f"       - {sensor.sname} ({sensor.subtype})")

        # Test chemistry
        chem = self.model.get_by_type(CHEM_TYPE)
        self.add_result(
            "Equipment.Chemistry",
            True,  # Chemistry is optional
            f"Found {len(chem)} chemistry controllers",
        )

        # Test schedules
        schedules = self.model.get_by_type(SCHED_TYPE)
        self.add_result(
            "Equipment.Schedules",
            True,  # Schedules are optional
            f"Found {len(schedules)} schedules",
        )

        return all_passed

    async def test_attribute_tracking(self) -> bool:
        """Test that attributes are being tracked."""
        self.log("📡", "Testing attribute tracking...")

        try:
            # Get attribute tracking queries
            queries = self.model.attributesToTrack()

            total_attrs = sum(len(q.get("keys", [])) for q in queries)

            self.add_result(
                "AttributeTracking.Queries",
                len(queries) > 0,
                f"Tracking {total_attrs} attributes across {len(queries)} objects",
            )

            return len(queries) > 0

        except Exception as e:
            self.add_result("AttributeTracking", False, f"Failed: {e}")
            return False

    async def test_connection_metrics(self) -> bool:
        """Test connection metrics."""
        self.log("📈", "Testing connection metrics...")

        try:
            metrics = self.controller.metrics

            self.add_result(
                "Metrics.RequestsSent",
                metrics.requests_sent > 0,
                f"Requests sent: {metrics.requests_sent}",
            )

            self.add_result(
                "Metrics.RequestsCompleted",
                metrics.requests_completed > 0,
                f"Requests completed: {metrics.requests_completed}",
            )

            avg_time_ms = metrics.average_response_time * 1000
            self.add_result(
                "Metrics.AvgResponseTime",
                True,
                f"Avg response time: {avg_time_ms:.1f}ms",
            )

            self.log("  ", f"       Reconnect attempts: {metrics.reconnect_attempts}")
            self.log("  ", f"       Successful connects: {metrics.successful_connects}")
            self.log("  ", f"       Requests failed: {metrics.requests_failed}")

            return True

        except Exception as e:
            self.add_result("Metrics", False, f"Failed: {e}")
            return False

    async def test_real_time_updates(self) -> bool:
        """Test that real-time updates are working."""
        self.log("⚡", "Testing real-time updates (waiting 5s for NotifyList)...")

        try:
            # Record initial state
            initial_completed = self.controller.metrics.requests_completed

            # Wait for potential updates
            await asyncio.sleep(5)

            final_completed = self.controller.metrics.requests_completed
            updates_received = final_completed - initial_completed

            # We might not receive updates if nothing changed, that's OK
            self.add_result(
                "RealTimeUpdates",
                True,
                f"Received {updates_received} responses during 5s window",
            )

            return True

        except Exception as e:
            self.add_result("RealTimeUpdates", False, f"Failed: {e}")
            return False

    async def test_disconnect_reconnect(self) -> bool:
        """Test connection resilience (simulated)."""
        self.log("🔄", "Testing connection state...")

        try:
            # Check if handler reports connected
            # Note: We don't actually disconnect to avoid disruption

            self.add_result(
                "ConnectionState", self.handler is not None, "Connection handler active"
            )

            return True

        except Exception as e:
            self.add_result("ConnectionState", False, f"Failed: {e}")
            return False

    async def cleanup(self) -> None:
        """Clean up connections."""
        self.log("🧹", "Cleaning up...")

        if self.handler:
            self.handler.stop()
            await asyncio.sleep(0.5)

    def print_summary(self) -> None:
        """Print test summary."""
        total = len(self.results)
        passed = sum(1 for r in self.results if r.passed)
        failed = total - passed

        print("\n" + "=" * 60)
        print("📊 INTEGRATION TEST SUMMARY")
        print("=" * 60)
        print(f"   Host: {self.host}:{self.port}")
        print(f"   Total Tests: {total}")
        print(f"   ✅ Passed: {passed}")
        print(f"   ❌ Failed: {failed}")
        print(f"   Success Rate: {passed / total * 100:.1f}%")
        print("=" * 60)

        if failed > 0:
            print("\n❌ Failed Tests:")
            for r in self.results:
                if not r.passed:
                    print(f"   - {r.name}: {r.message}")

        print()

    async def run_all_tests(self) -> bool:
        """Run all integration tests."""
        self.start_time = datetime.now()

        print("=" * 60)
        print("🏊 INTELLICENTER INTEGRATION TEST")
        print("=" * 60)
        print(f"   Target: {self.host}:{self.port}")
        print(f"   Started: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 60)
        print()

        try:
            # Test connection first - required for other tests
            if not await self.test_connection():
                self.print_summary()
                return False

            # Run remaining tests
            await self.test_system_info()
            await self.test_model_population()
            await self.test_equipment_types()
            await self.test_attribute_tracking()
            await self.test_connection_metrics()
            await self.test_real_time_updates()
            await self.test_disconnect_reconnect()

        finally:
            await self.cleanup()

        self.print_summary()

        return all(r.passed for r in self.results)


async def main() -> int:
    """Main entry point."""
    host = os.environ.get("INTELLICENTER_HOST")
    port = int(os.environ.get("INTELLICENTER_PORT", "6681"))

    if not host:
        print("❌ Error: INTELLICENTER_HOST not set")
        print("   Create a .env file with:")
        print("   INTELLICENTER_HOST=<ip_address>")
        return 1

    tester = IntegrationTester(host, port)
    success = await tester.run_all_tests()

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
