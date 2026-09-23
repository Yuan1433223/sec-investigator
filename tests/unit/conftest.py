"""Shared fixtures for Phase 6 unit tests."""
import pytest

from kks_runtime.config.settings import Settings


@pytest.fixture
def test_settings() -> Settings:
    """Minimal Settings with fake URLs — never hits real services."""
    return Settings(
        cc_api_url="http://fake-cc",
        cc_api_key="test-cc-key",
        cc_request_timeout=5,
        ddos_api_url="http://fake-ddos",
        ddos_api_key="test-ddos-key",
        ddos_token="test-ddos-token",
        ddos_request_timeout=5,
        es_url="http://fake-es:9200",
        es_username="",
        es_password="",
        prometheus_url="http://fake-prom:9090",
        prometheus_request_timeout=5,
        prometheus_node_port=9100,
        waf_api_url="http://fake-waf",
        waf_api_token="test-waf-token",
        waf_request_timeout=5,
        gf_yxd_api_url="http://fake-gf-yxd",
        gf_yxd_api_xtoken="test-yxd-token",
        gf_cdn_api_url="http://fake-gf-cdn",
        gf_cdn_api_xtoken="test-cdn-token",
        gf_ddos_api_url="http://fake-gf-ddos",
        gf_ddos_api_xtoken="test-gf-ddos-token",
        gf_request_timeout=5,
        # Attack thresholds (explicit for policy tests)
        cc_attack_pps_threshold=2000,
        cc_attack_delta_threshold=1000,
        ddos_attack_kbps_threshold=1_000_000,
    )
