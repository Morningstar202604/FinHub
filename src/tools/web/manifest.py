"""Compatibility shim — the web provider manifest moved to ``src.config``.

The manifest is provider *metadata* (capabilities, tiers, pricing), not a
capability itself. It now lives in ``config.web_manifest`` because its
consumers are config/policy layers: the LLM resolve-time tier gate, the
user-preference write validation, and the cost table. Filing it under ``tools``
made the capability layer own a type the application shell imports, which is
the `server -> tools` inversion tracked by ``scripts/guard/layering_guard.py``.

New code should import from ``src.config.web_manifest`` directly. This module
re-exports the same objects so the tool-side callers (``search.py``,
``crawl.py``, ``router.py``, ``research.py``) keep working unchanged, and so no
second copy of the manifest ever exists — ``_load_manifest`` is ``lru_cache``d
by identity, and two module identities would mean two caches.
"""

from src.config.web_manifest import (  # noqa: F401
    CAPABILITY_CRAWL,
    CAPABILITY_FETCH,
    CAPABILITY_MAP,
    CAPABILITY_RESEARCH,
    CAPABILITY_SEARCH,
    CapabilitySpec,
    LevelSpec,
    WebProviderSpec,
    get_auxiliary_pricing,
    get_capability,
    get_web_provider_spec,
    get_web_providers,
    providers_with_capability,
    resolve_min_tier,
)

__all__ = [
    "CAPABILITY_CRAWL",
    "CAPABILITY_FETCH",
    "CAPABILITY_MAP",
    "CAPABILITY_RESEARCH",
    "CAPABILITY_SEARCH",
    "CapabilitySpec",
    "LevelSpec",
    "WebProviderSpec",
    "get_auxiliary_pricing",
    "get_capability",
    "get_web_provider_spec",
    "get_web_providers",
    "providers_with_capability",
    "resolve_min_tier",
]
