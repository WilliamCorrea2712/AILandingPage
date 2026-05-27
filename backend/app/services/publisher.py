"""
Publisher — provisions subdomain, SSL and Cloudflare CDN for landing pages.

Requirements: 8.1–8.7
"""
from __future__ import annotations

import logging
import re
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import httpx

from app.config import settings
from app.exceptions import CDNIntegrationError, PublicationTimeoutError, SSLProvisioningError

if TYPE_CHECKING:
    from app.models.project import Project
    from app.services.renderer import RenderResult

logger = logging.getLogger(__name__)

PUBLICATION_TIMEOUT_SECONDS = 300  # 5 minutes
CDN_TTL = 3600  # seconds


@dataclass
class DNSInstructions:
    record_type: str
    name: str
    value: str
    ttl: int = 3600


@dataclass
class PublicationResult:
    url: str
    subdomain: str
    ssl_status: str
    cdn_status: str
    published_at: datetime


def _slugify(name: str) -> str:
    """Convert project name to URL-safe slug."""
    slug = name.lower().strip()
    slug = re.sub(r'[^\w\s-]', '', slug)
    slug = re.sub(r'[\s_]+', '-', slug)
    slug = re.sub(r'-+', '-', slug)
    return slug.strip('-')


class Publisher:
    def publish(self, project: "Project", render_result: "RenderResult") -> PublicationResult:
        start = time.monotonic()
        slug = _slugify(project.name)
        subdomain = f"{slug}.{settings.PLATFORM_DOMAIN}"

        # Step 1: Provision subdomain + SSL
        ssl_status = self._provision_ssl(subdomain)

        # Step 2: Integrate CDN
        cdn_status = self._integrate_cdn(subdomain, render_result)

        elapsed = time.monotonic() - start
        if elapsed > PUBLICATION_TIMEOUT_SECONDS:
            raise PublicationTimeoutError(
                f"Publicação excedeu o tempo limite de 5 minutos. "
                f"Estado atual: SSL={ssl_status}, CDN={cdn_status}"
            )

        return PublicationResult(
            url=f"https://{subdomain}",
            subdomain=subdomain,
            ssl_status=ssl_status,
            cdn_status=cdn_status,
            published_at=datetime.now(tz=timezone.utc),
        )

    def _provision_ssl(self, subdomain: str) -> str:
        """Provision SSL certificate via Cloudflare API."""
        if not settings.CLOUDFLARE_API_TOKEN or not settings.CLOUDFLARE_ZONE_ID:
            logger.warning("Cloudflare credentials not configured. Skipping SSL provisioning.")
            return "skipped"

        try:
            with httpx.Client(timeout=30) as client:
                # Create DNS record
                resp = client.post(
                    f"https://api.cloudflare.com/client/v4/zones/{settings.CLOUDFLARE_ZONE_ID}/dns_records",
                    headers={"Authorization": f"Bearer {settings.CLOUDFLARE_API_TOKEN}"},
                    json={
                        "type": "CNAME",
                        "name": subdomain,
                        "content": settings.PLATFORM_DOMAIN,
                        "ttl": 1,
                        "proxied": True,
                    },
                )
                if resp.status_code not in (200, 201):
                    raise SSLProvisioningError(
                        f"Falha ao criar registro DNS para {subdomain}. "
                        f"Motivo: {resp.text}. "
                        f"Instruções: Crie manualmente um registro CNAME apontando {subdomain} para {settings.PLATFORM_DOMAIN}."
                    )
            return "active"
        except SSLProvisioningError:
            raise
        except Exception as exc:
            raise SSLProvisioningError(
                f"Falha ao provisionar SSL para {subdomain}: {exc}. "
                f"Instruções: Verifique as credenciais Cloudflare e tente novamente."
            ) from exc

    def _integrate_cdn(self, subdomain: str, render_result: "RenderResult") -> str:
        """Configure Cloudflare CDN cache rules."""
        if not settings.CLOUDFLARE_API_TOKEN or not settings.CLOUDFLARE_ZONE_ID:
            logger.warning("Cloudflare credentials not configured. Skipping CDN integration.")
            return "skipped"

        try:
            with httpx.Client(timeout=30) as client:
                resp = client.post(
                    f"https://api.cloudflare.com/client/v4/zones/{settings.CLOUDFLARE_ZONE_ID}/cache/variants",
                    headers={"Authorization": f"Bearer {settings.CLOUDFLARE_API_TOKEN}"},
                    json={"value": {"ttl": CDN_TTL}},
                )
                if resp.status_code not in (200, 201):
                    raise CDNIntegrationError(
                        f"Falha ao configurar CDN para {subdomain}: {resp.text}"
                    )
            return "active"
        except CDNIntegrationError:
            raise
        except Exception as exc:
            raise CDNIntegrationError(f"Falha na integração com CDN Cloudflare: {exc}") from exc

    def configure_custom_domain(self, fqdn: str) -> DNSInstructions:
        """Return DNS instructions for a custom domain."""
        return DNSInstructions(
            record_type="CNAME",
            name=fqdn,
            value=settings.PLATFORM_DOMAIN,
            ttl=3600,
        )
