"""
Tests for OSIRIS Benchmark Suite (osiris_benchmark_suite.py)
"""
import unittest
import os
import json
from osiris_benchmark_suite import BenchmarkRunner, BENCHMARK_TASKS, BASELINE_METRICS

class TestBenchmarkRunner(unittest.TestCase):
    def setUp(self):
        self.runner = BenchmarkRunner(user_id="test")

    def test_run_task_mock(self):
        # Use a simple task and patch UltraCoderSwarm to mock output
        from unittest.mock import patch, MagicMock
        task = BENCHMARK_TASKS["code_gen"][0]
        mock_swarm = MagicMock()
        mock_swarm.solve.return_value = MagicMock(
            performance_metrics={"quality": 0.8, "refinement_cycles": 1, "agents_used": 9},
            solution=json.dumps({"plan": {"plan": True}, "implementation": {"code_produced": True}, "critique": {"quality_score": 1.0}})
        )
        with patch("osiris_benchmark_suite.UltraCoderSwarm", return_value=mock_swarm):
            import asyncio
            result = asyncio.run(self.runner.run_task(task))
            self.assertTrue(result.passed)
            self.assertGreaterEqual(result.quality_score, 0.7)
            self.assertEqual(result.category, "code_gen")

    def test_run_suite_mock(self):
        # Patch UltraCoderSwarm to always return a passing result
        from unittest.mock import patch, MagicMock
        mock_swarm = MagicMock()
        mock_swarm.solve.return_value = MagicMock(
            performance_metrics={"quality": 0.9, "refinement_cycles": 1, "agents_used": 9},
            solution=json.dumps({"plan": {"plan": True}, "implementation": {"code_produced": True}, "critique": {"quality_score": 1.0}})
        )
        with patch("osiris_benchmark_suite.UltraCoderSwarm", return_value=mock_swarm):
            import asyncio
            suite_result = asyncio.run(self.runner.run_suite(suite_name="code_gen"))
            self.assertGreaterEqual(suite_result.avg_quality, 0.7)
            self.assertEqual(suite_result.suite_name, "code_gen")
            self.assertGreaterEqual(suite_result.passed, 1)

    def test_baseline_metrics(self):
        self.assertIn("copilot", BASELINE_METRICS)
        self.assertIn("code_gen", BASELINE_METRICS["copilot"])

if __name__ == "__main__":
    unittest.main()
