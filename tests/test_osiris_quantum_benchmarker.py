"""
Tests for OSIRIS Quantum Hardware Benchmarker (osiris_quantum_benchmarker.py)
"""
import unittest
import os
from osiris_quantum_benchmarker import QuantumHardwareBenchmarker

class TestQuantumHardwareBenchmarker(unittest.TestCase):
    def setUp(self):
        self.benchmarker = QuantumHardwareBenchmarker(api_token=None)

    def test_mock_mode(self):
        self.assertTrue(self.benchmarker.mock_mode)

    def test_benchmark_backend_mock(self):
        results = self.benchmarker.benchmark_backend("ibm_torino", extreme_mode=False)
        self.assertIsInstance(results, list)
        self.assertGreaterEqual(len(results), 1)
        for r in results:
            self.assertGreaterEqual(r.avg_fidelity, 0)
            self.assertGreaterEqual(r.xeb_score, 0)
            self.assertGreaterEqual(r.error_rate, 0)
            self.assertIsInstance(r.job_ids, list)

    def test_generate_report(self):
        self.benchmarker.benchmark_backend("ibm_torino", extreme_mode=False)
        report = self.benchmarker.generate_report()
        self.assertIn("QUANTUM HARDWARE BENCHMARK REPORT", report)

if __name__ == "__main__":
    unittest.main()
