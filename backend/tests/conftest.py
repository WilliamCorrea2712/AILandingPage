"""
Test configuration and fixtures.

Requirements: all
"""
from hypothesis import settings, HealthCheck

# Hypothesis profiles
settings.register_profile("ci", max_examples=100, suppress_health_check=[HealthCheck.too_slow])
settings.register_profile("dev", max_examples=50, suppress_health_check=[HealthCheck.too_slow])
settings.load_profile("ci")
