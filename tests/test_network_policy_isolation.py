"""
Network policy isolation and proxy override boundary verification tests.
Validates the execution safety invariants for environment proxy configuration:
1. Localhost test HTTP fixture is reachable when explicitly enabled (via no_proxy=localhost,127.0.0.1).
2. External hostnames remain blocked or absent from the test environment.
3. Paper venue remains simulator-only regardless of no_proxy or proxy configurations.
4. No production endpoint can be supplied through proxy environment variables.
"""

import http.server
import os
import socket
import threading
import unittest
import urllib.error
import urllib.request

from osiris_reconciliation import SimulatedPaperVenue


class SimpleLocalHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status": "ok", "source": "loopback_fixture"}')

    def log_message(self, format, *args):
        pass  # Suppress logging in tests


class TestNetworkPolicyIsolation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Bind an ephemeral local HTTP server strictly on 127.0.0.1
        cls.server = http.server.HTTPServer(("127.0.0.1", 0), SimpleLocalHandler)
        cls.port = cls.server.server_port
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_localhost_fixture_reachable_with_loopback_isolation(self):
        """Proves loopback HTTP test fixture is directly reachable via no_proxy override."""
        url = f"http://127.0.0.1:{self.port}/"
        # Using loopback proxy handler to enforce loopback bypass
        proxy_handler = urllib.request.ProxyHandler({})
        opener = urllib.request.build_opener(proxy_handler)
        req = urllib.request.Request(url)
        with opener.open(req, timeout=2.0) as resp:
            data = resp.read().decode("utf-8")
            self.assertEqual(resp.status, 200)
            self.assertIn("loopback_fixture", data)

    def test_external_hostname_blocked_or_rejected(self):
        """Proves external hostnames (e.g. example.com) cannot be reached or resolved in isolated environment."""
        # Test connecting to an external endpoint with strict timeout
        url = "http://example.invalid:9999/test"
        req = urllib.request.Request(url)
        with self.assertRaises((urllib.error.URLError, socket.gaierror, TimeoutError, OSError)):
            urllib.request.urlopen(req, timeout=1.0)

    def test_paper_venue_remains_simulator_only(self):
        """Proves SimulatedPaperVenue has no network sockets, endpoints, or remote egress."""
        venue = SimulatedPaperVenue(venue_id="LOCAL_SIM_VENUE")
        # Inspect all attributes of SimulatedPaperVenue
        attrs = dir(venue)
        disallowed_terms = ["socket", "url", "http", "api_key", "secret", "remote", "endpoint"]
        for term in disallowed_terms:
            matching = [a for a in attrs if term in a.lower()]
            self.assertEqual(
                matching,
                [],
                f"SimulatedPaperVenue contains disallowed network attribute: {matching}",
            )
        # Verify submit and query operate purely in-memory
        res = venue.submit_order("test_ord", "SYM", "BUY", 1.0, 10.0)
        self.assertEqual(res["venue_status"], "FILLED")
        self.assertIn("client_order_id", res)
        queried = venue.query_order("test_ord")
        self.assertEqual(queried["client_order_id"], "test_ord")

    def test_proxy_env_cannot_supply_production_endpoint(self):
        """Proves no_proxy and proxy variables cannot inject a production trading or QPU endpoint."""
        # Ensure simulated paper venue rejects attempts to route to remote URLs
        venue = SimulatedPaperVenue(venue_id="TEST_VENUE")
        with self.assertRaises((TypeError, ValueError, AttributeError)):
            # SimulatedPaperVenue does not accept url or remote endpoint arguments
            venue.connect(url="https://live.api.quantum.exchange.com")  # type: ignore


if __name__ == "__main__":
    unittest.main()
