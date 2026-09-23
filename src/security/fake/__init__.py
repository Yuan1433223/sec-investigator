"""Fake data-source layer (DATA_SOURCE=fake).

Serves realistic synthetic data derived from the recorded incidents
(``docs/incidents.md``) so the whole investigation graph runs offline, without
any enterprise VPN or ES/Prometheus/WAF/GF system. See :mod:`security.fake.client`
for the seam and :mod:`security.fake.transport` for the request handler.
"""

from security.fake.client import build_async_client

__all__ = ["build_async_client"]
