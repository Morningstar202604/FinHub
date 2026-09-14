"""Core configuration classes for Open PTC Agent infrastructure.

This module defines pure data classes for core configuration:
- Daytona sandbox settings
- MCP server configurations
- Filesystem access settings
- Security settings
- Logging settings
"""

import logging
import re
import sys
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

logger = logging.getLogger(__name__)

# Executables an MCP stdio server may be launched with. This list is a hard
# allow-list, not a denylist: `command` comes from workspace/user config, which
# is untrusted, and it is passed to subprocess.Popen inside the backend
# process — which holds the Docker socket. Anything outside this set
# (/bin/bash, python with a path payload, a stray .sh) would be arbitrary
# command execution with the backend's privileges.
_MCP_ALLOWED_COMMANDS = frozenset(
    {
        # Node ecosystem
        "npx",
        "node",
        "bunx",
        "bun",
        "deno",
        # Python ecosystem
        "uvx",
        "uv",
        "python",
        "python3",
        "pipx",
        # Go / Rust single-binary servers, commonly shipped this way
        "go",
        "cargo",
        # Containerised servers
        "docker",
    }
)

# A bare name only — no directory component, no extension. This rejects
# `/bin/bash`, `./evil.sh`, `../../tmp/x`, and `C:\evil.exe` in one rule.
_MCP_COMMAND_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

# Builtin plugins ship inside this repository and their servers are code the
# operator reviewed, so they may point at the project's own interpreter
# (`.venv/bin/python`) instead of a PATH lookup. That exception is narrow on
# purpose: a relative python path within the project, or an absolute path
# *inside one of these trusted roots*, with no traversal. Everything else
# still has to be allow-listed.
#
# The absolute case exists because `sys.executable` is how a process hands its
# own interpreter to a child, and that is a legitimate thing for first-party
# code to do. It is gated on the path living under the app dir, so
# `/usr/bin/bash` and `/tmp/evil` both still fail.
_TRUSTED_INTERPRETER_ROOTS = ("/app/", "/usr/local/bin/python", "/usr/bin/python")
_MCP_PYTHON_BASENAME_RE = re.compile(r"^python3?(?:\.\d+)?$")


def _is_trusted_builtin_command(raw: str) -> bool:
    """True when a *builtin* server points at a trusted python interpreter.

    Accepts two shapes, and nothing else:

    - a project-relative path ending in a python basename, e.g.
      ``.venv/bin/python`` (how every bundled plugin launches its server);
    - an absolute path ending in a python basename that lives under a trusted
      root, e.g. ``/app/.venv/bin/python3`` (``sys.executable``).

    Traversal segments and every other executable are rejected, so this cannot
    be used to reach ``/bin/bash`` or a payload in ``/tmp``.
    """
    if ".." in raw.split("/"):
        return False

    if raw.startswith("/"):
        if not _MCP_PYTHON_BASENAME_RE.match(raw.rsplit("/", 1)[-1]):
            return False
        # A process handing its OWN interpreter to a child is first-party by
        # definition — sys.executable cannot be less trusted than the process
        # already running. The roots above are only the shapes that takes in
        # the container image; hard-coding them alone makes any other install
        # prefix (a bare-metal /opt, a local checkout) unable to launch its
        # own bundled servers.
        if raw == sys.executable:
            return True
        return raw.startswith(_TRUSTED_INTERPRETER_ROOTS)

    return bool(_MCP_PYTHON_BASENAME_RE.match(raw.rsplit("/", 1)[-1]))


def validate_mcp_command(command: str | None, *, source: str = "builtin") -> str | None:
    """Validate an MCP stdio server's ``command``.

    The rule depends on where the server came from:

    - ``builtin``: shipped in this repo. A project-relative python interpreter
      (``.venv/bin/python``) is accepted, because that is how every bundled
      plugin launches its server.
    - ``workspace`` / ``user``: untrusted, authored by a workspace owner. Only a
      bare allow-listed executable name is accepted — no paths at all.

    Returns the normalised command, or raises ``ValueError`` naming the
    offending value. Exposed as a module function so both the Pydantic model
    and the runtime spawn path can call the same rule.
    """
    if command is None:
        return None

    raw = command.strip()
    if not raw:
        return None

    if source == "builtin" and _is_trusted_builtin_command(raw):
        return raw

    if not _MCP_COMMAND_NAME_RE.match(raw):
        raise ValueError(
            f"MCP server command {raw!r} must be a bare executable name; "
            "paths (absolute, relative, or with an extension) are not allowed"
        )

    if raw not in _MCP_ALLOWED_COMMANDS:
        allowed = ", ".join(sorted(_MCP_ALLOWED_COMMANDS))
        raise ValueError(
            f"MCP server command {raw!r} is not allow-listed; permitted: {allowed}"
        )

    return raw


# Default security lists — used by SecurityConfig defaults and create_default_security_config()
DEFAULT_ALLOWED_IMPORTS = [
    "os", "sys", "json", "yaml", "requests", "datetime",
    "pathlib", "typing", "re", "math", "random", "time",
    "collections", "itertools", "functools", "subprocess", "shutil",
]

DEFAULT_BLOCKED_PATTERNS: list[str] = []


# Organization resource ceiling — every tier is clamped to these maxima.
# cpu in vCPU cores, memory in GiB, disk in GiB.
RESOURCE_TIER_CEILING = {"cpu": 4, "memory": 8, "disk": 10}


class ResourceTier(BaseModel):
    """A named sandbox resource preset (vCPU cores, memory GiB, disk GiB)."""

    cpu: int = Field(ge=1)
    memory: int = Field(ge=1)
    disk: int = Field(ge=1)


def _default_resource_tiers() -> dict[str, ResourceTier]:
    return {
        "standard": ResourceTier(cpu=1, memory=1, disk=3),
        "performance": ResourceTier(cpu=2, memory=4, disk=5),
        "max": ResourceTier(cpu=4, memory=8, disk=10),
    }


class DaytonaConfig(BaseModel):
    """Daytona sandbox configuration.

    All fields have sensible defaults. Only api_key needs to be set
    (via DAYTONA_API_KEY environment variable).
    """

    api_key: str = ""  # Set via DAYTONA_API_KEY env var, validated later
    base_url: str = "https://app.daytona.io/api"
    secret_namespace: str = ""  # Set via DAYTONA_SECRET_NAMESPACE
    auto_stop_interval: int = 3600  # 1 hour
    auto_archive_interval: int = 604800  # 7 days — keep stopped (fast restart) before cold storage
    auto_delete_interval: int = 7776000  # 90 days — total dormant lifetime
    python_version: str = "3.12"

    # Snapshot configuration for faster sandbox initialization
    snapshot_enabled: bool = True
    snapshot_name: str | None = None
    snapshot_auto_create: bool = True

    # Resource tier presets (operator-tunable in agent_config.yaml).
    default_tier: str = "standard"
    resource_tiers: dict[str, ResourceTier] = Field(
        default_factory=_default_resource_tiers, validate_default=True
    )

    @field_validator("resource_tiers")
    @classmethod
    def _clamp_tiers_to_ceiling(
        cls, v: dict[str, ResourceTier]
    ) -> dict[str, ResourceTier]:
        """Clamp every tier to the org ceiling (clamp, never reject)."""
        for name, tier in v.items():
            for resource, ceiling in RESOURCE_TIER_CEILING.items():
                value = getattr(tier, resource)
                if value > ceiling:
                    logger.warning(
                        "resource_tiers[%r].%s=%s exceeds the org ceiling %s; clamping",
                        name, resource, value, ceiling,
                    )
                    setattr(tier, resource, ceiling)
        return v

    @model_validator(mode="after")
    def _default_tier_must_exist(self) -> "DaytonaConfig":
        """The default tier must resolve to a real preset — the create path
        relies on it to size base sandboxes, so a missing default is a config bug."""
        if self.default_tier not in self.resource_tiers:
            raise ValueError(
                f"default_tier {self.default_tier!r} is not defined in "
                f"resource_tiers (available: {sorted(self.resource_tiers)})"
            )
        return self


class SecurityConfig(BaseModel):
    """Security configuration for code execution.

    All fields have sensible defaults for safe code execution.
    """

    max_execution_time: int = 300  # 5 minutes
    max_code_length: int = 10000
    max_file_size: int = 10485760  # 10MB
    enable_code_validation: bool = True
    allowed_imports: list[str] = Field(
        default_factory=lambda: list(DEFAULT_ALLOWED_IMPORTS)
    )
    blocked_patterns: list[str] = Field(
        default_factory=lambda: list(DEFAULT_BLOCKED_PATTERNS)
    )


class VaultBlueprint(BaseModel):
    """Credential an MCP server expects users to set in the workspace vault.

    Pure metadata — never touches actual values. Surfaced via
    GET /api/v1/workspaces/{id}/vault/blueprints as a 'recommended but not set'
    list in the UI's Vault tab, so users don't have to read docs to learn the
    exact secret name for each integration.
    """

    # Same regex as CreateSecretRequest in src/server/models/vault.py.
    # Blueprint name becomes a vault key, so it must satisfy the same rule.
    # The regex's {0,63} already caps length at 64 — no separate max_length needed.
    name: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
    label: str = Field(..., min_length=1, max_length=80)
    # max_length matches CreateSecretRequest.description in src/server/models/vault.py
    # so that pre-filling the add-secret form from a blueprint never produces a
    # description that the create endpoint would reject with a 422.
    description: str = Field("", max_length=256)
    docs_url: str | None = None
    # Optional client-side hint for the secret *value*. Stored as a string (not
    # compiled at runtime on the value) because it ships to the frontend for
    # validation. The backend never runs it against values — keeps secrets opaque.
    regex: str | None = None

    @field_validator("regex")
    @classmethod
    def _validate_regex_compiles(cls, v: str | None) -> str | None:
        """Fail-fast at config-load time if an operator typos the pattern."""
        if v is None:
            return v
        try:
            re.compile(v)
        except re.error as exc:
            raise ValueError(f"vault_blueprint regex is not a valid pattern: {exc}")
        return v

    @field_validator("docs_url")
    @classmethod
    def _validate_docs_url_scheme(cls, v: str | None) -> str | None:
        # docs_url renders directly into an <a href>; rel=noopener noreferrer
        # does not block javascript:/data: schemes, so reject them at load time.
        if v is None:
            return v
        if not (v.startswith("https://") or v.startswith("http://")):
            raise ValueError("vault_blueprint docs_url must start with https:// or http://")
        return v


class MCPServerConfig(BaseModel):
    """Configuration for a single MCP server."""

    name: str
    enabled: bool = True  # Whether this server is enabled (default: True)
    description: str = ""  # What the MCP server does
    instruction: str = ""  # When/how to use this server
    transport: Literal["stdio", "sse", "http"] = "stdio"
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    url: str | None = None  # For SSE/HTTP transports
    headers: dict[str, str] = Field(default_factory=dict)  # For SSE/HTTP transports
    tool_exposure_mode: Literal["summary", "detailed"] | None = None  # Per-server override
    vault_blueprints: list[VaultBlueprint] = Field(default_factory=list)
    # 'builtin' = from agent_config.yaml; 'workspace' = user-configured per-workspace;
    # 'user' = user-level server inherited by every workspace of the user.
    # Workspace AND user servers are untrusted: vault-only secret resolution,
    # neutral prompt framing, sanitized discovery.
    source: Literal["builtin", "workspace", "user"] = "builtin"
    discovery_uses_secrets: bool = False  # workspace servers: resolve vault secrets during discovery (default off = secret-less probe)
    # Set at resolve time when the user has a non-revoked OAuth connection for
    # this server — the server is then bound through the egress relay and its
    # sandbox config carries a grant reference instead of the vendor URL.
    oauth_connection_id: str | None = None

    @model_validator(mode="after")
    def _check_command(self) -> "MCPServerConfig":
        """Reject non-allow-listed executables at config-load time.

        Fail here rather than at spawn time so a bad server never reaches the
        process table, and so the error surfaces where the operator can see it.
        A model validator (not a field validator) is used because the rule
        depends on `source`, and field validators see sibling fields in
        declaration order only.
        """
        if self.command is None:
            return self
        object.__setattr__(
            self, "command", validate_mcp_command(self.command, source=self.source)
        )
        return self


class MCPConfig(BaseModel):
    """MCP server configurations.

    By default, no MCP servers are configured. Add servers to enable
    additional tools for the agent.
    """

    servers: list[MCPServerConfig] = Field(default_factory=list)
    tool_discovery_enabled: bool = True
    lazy_load: bool = True
    cache_duration: int | None = None
    tool_exposure_mode: Literal["summary", "detailed"] = "summary"


class LoggingConfig(BaseModel):
    """Logging configuration with sensible defaults."""

    level: str = "INFO"
    file: str = "logs/ptc.log"


class FilesystemConfig(BaseModel):
    """Filesystem access configuration for first-class filesystem tools.

    ``allowed_directories`` and ``denied_directories`` are derived from
    ``working_directory`` by default so you only need to set one value.

    Note: this validation is enforced for first-class filesystem tools only.
    """

    working_directory: str = "/home/workspace"
    allowed_directories: list[str] | None = None
    denied_directories: list[str] | None = None
    enable_path_validation: bool = True

    def model_post_init(self, __context: Any) -> None:
        """Derive allowed/denied directories from working_directory when not set."""
        if self.allowed_directories is None:
            self.allowed_directories = [self.working_directory, "/tmp"]
        if self.denied_directories is None:
            self.denied_directories = [f"{self.working_directory}/_internal"]


def validate_daytona_api_key(daytona: DaytonaConfig) -> None:
    """Validate that the Daytona API key is present.

    Raises:
        ValueError: If the API key is missing
    """
    if not daytona.api_key:
        raise ValueError(
            "Missing required credentials in .env file:\n"
            "  - DAYTONA_API_KEY\n"
            "Please add these credentials to your .env file."
        )


class DockerConfig(BaseModel):
    """Docker sandbox provider configuration.

    Mount options (combined freely):

    * **dev_mode + host_work_dir** — bind-mount a host directory as the
      sandbox working directory.  Files appear on both sides instantly.
    * **volumes** — arbitrary extra mounts in Docker bind format
      (``"host_path:container_path[:ro]"``).  Useful for datasets, models,
      or credentials that should be available inside the sandbox.

    Examples::

        # Dev mode — edit files on host, see changes in sandbox
        docker:
          dev_mode: true
          host_work_dir: "/Users/me/project/sandbox-work"

        # Extra read-only data mount
        docker:
          volumes:
            - "/data/datasets:/mnt/datasets:ro"

        # Both
        docker:
          dev_mode: true
          host_work_dir: "/Users/me/work"
          volumes:
            - "/data/models:/mnt/models:ro"
            - "/secrets/keys:/run/secrets:ro"
    """

    image: str = "finhub-sandbox:latest"
    working_dir: str = "/home/workspace"  # fallback; filesystem.working_directory is authoritative
    memory_limit: str = "4g"
    cpu_count: float = 2.0
    dev_mode: bool = False
    host_work_dir: str | None = None
    volumes: list[str] = Field(default_factory=list)
    network_mode: str = "bridge"
    preview_proxy_ports: str = "13000-13009"
    preview_base_url: str | None = None


class SandboxQuotas(BaseModel):
    """Per-workspace-per-user sandbox quotas (ROADMAP M2-C).

    All fields are upper bounds; a value of None (default) means "no limit"
    for that dimension, so the default deploy behaves exactly as before.
    ``memory_mb`` and ``cpu_share`` are advisory targets used by the
    sandbox-budget guard (single-run limits), while ``max_workspaces`` /
    ``max_parallel_runs`` / ``idle_minutes`` bound the fleet.
    """

    max_workspaces: int | None = None
    max_parallel_runs: int | None = None
    cpu_share: int | None = None
    memory_mb: int | None = None
    idle_minutes: int | None = None

    @field_validator(
        "max_workspaces",
        "max_parallel_runs",
        "cpu_share",
        "memory_mb",
        "idle_minutes",
    )
    @classmethod
    def _non_negative(cls, v: int | None) -> int | None:
        if v is not None and v < 0:
            raise ValueError("quota values must be >= 0")
        return v


class SandboxQuotaError(Exception):
    """Raised when a sandbox quota (M2-C) is exceeded.

    Carries the human-readable detail the API layer turns into a 409.
    """

    def __init__(self, message: str, *, current: int, limit: int) -> None:
        super().__init__(message)
        self.message = message
        self.current = current
        self.limit = limit


def assert_sandbox_quotas(
    quota: SandboxQuotas,
    *,
    workspace_count: int = 0,
    running_count: int = 0,
) -> None:
    """Enforce per-user sandbox fleet quotas; raise :class:`SandboxQuotaError`.

    Only the fields with a configured limit are checked — unbounded fields
    (None) never fire, so deployments without a ``sandbox.quotas`` block keep
    their current behavior. This is the M2-C 409 gate: create/start call it
    with live row counts before provisioning.
    """
    if quota.max_workspaces is not None and workspace_count >= quota.max_workspaces:
        raise SandboxQuotaError(
            f"沙箱工作区数量已达上限（{workspace_count}/{quota.max_workspaces}）。"
            "请删除不再使用的旧工作区后再创建。",
            current=workspace_count,
            limit=quota.max_workspaces,
        )
    if quota.max_parallel_runs is not None and running_count >= quota.max_parallel_runs:
        raise SandboxQuotaError(
            f"同时运行中的工作区已达上限（{running_count}/{quota.max_parallel_runs}）。"
            "请等待运行中的任务结束。",
            current=running_count,
            limit=quota.max_parallel_runs,
        )


class PlatformSecretDefinition(BaseModel):
    """One backend-owned platform credential, declared in agent_config.yaml.

    The set of entries is the deployment's platform-secret catalog: convergence,
    certification, and the fleet generation all operate on every entry at once,
    and any set change registers as an identity change that re-pends the fleet.
    Declared in deployment config (not code) so the OSS repo reveals the
    mechanism without the hosted vendor list.
    """

    model_config = ConfigDict(frozen=True)

    source_env_var: str
    sandbox_env_var: str
    name_suffix: str
    description: str
    hosts: tuple[str, ...]

    @field_validator("source_env_var", "sandbox_env_var")
    @classmethod
    def _validate_env_var(cls, v: str) -> str:
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", v):
            raise ValueError(f"invalid environment variable name: {v!r}")
        return v

    @field_validator("name_suffix")
    @classmethod
    def _validate_name_suffix(cls, v: str) -> str:
        # Length-bounded so the derived Secret name (namespace + '-' + suffix)
        # stays under the provider/DB limit enforced in resolve_platform_secrets.
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]{0,62}", v):
            raise ValueError(f"invalid Secret name suffix: {v!r}")
        return v

    @field_validator("hosts")
    @classmethod
    def _validate_hosts(cls, v: tuple[str, ...]) -> tuple[str, ...]:
        if not v:
            raise ValueError("hosts must name at least one egress target")
        for host in v:
            if not re.fullmatch(r"[a-z0-9]([a-z0-9.-]*[a-z0-9])?", host):
                raise ValueError(f"invalid egress host: {host!r}")
        return v


class SandboxConfig(BaseModel):
    """Provider-agnostic sandbox configuration wrapper."""

    provider: Literal["daytona", "docker", "memory"] = "daytona"
    daytona: DaytonaConfig = Field(default_factory=DaytonaConfig)
    docker: DockerConfig = Field(default_factory=DockerConfig)
    platform_secrets: tuple[PlatformSecretDefinition, ...] = ()
    # Per-user sandbox quotas (M2-C). None = unbounded, preserving legacy
    # behavior for deployments that don't configure the block.
    quotas: SandboxQuotas = Field(default_factory=SandboxQuotas)

    @model_validator(mode="after")
    def _validate_unique_platform_secrets(self) -> "SandboxConfig":
        # Both keys must be unique across the catalog: a duplicate
        # sandbox_env_var collapses the binding map (and collides the rollout
        # row keyed on it), and a duplicate name_suffix resolves two entries to
        # one provider Secret — either silently mounts the wrong credential.
        for field in ("sandbox_env_var", "name_suffix"):
            values = [getattr(d, field) for d in self.platform_secrets]
            duplicates = sorted({v for v in values if values.count(v) > 1})
            if duplicates:
                raise ValueError(
                    f"duplicate {field} in platform_secrets: {duplicates}"
                )
        return self


class CoreConfig(BaseModel):
    """Core infrastructure configuration.

    Contains settings for sandbox, MCP servers, filesystem, security, and logging.
    LLM configuration is handled separately in src/config/agent.py.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    # Sub-configurations
    sandbox: SandboxConfig
    security: SecurityConfig
    mcp: MCPConfig
    logging: LoggingConfig
    filesystem: FilesystemConfig
    config_file_dir: Path | None = Field(default=None, exclude=True)

    @property
    def daytona(self) -> DaytonaConfig:
        """Backward-compat shim: config.daytona -> config.sandbox.daytona."""
        return self.sandbox.daytona

    def validate_api_keys(self) -> None:
        """Validate that required API keys are present.

        Raises:
            ValueError: If required API keys are missing
        """
        if self.sandbox.provider == "daytona":
            validate_daytona_api_key(self.sandbox.daytona)


def create_default_security_config() -> SecurityConfig:
    """Create SecurityConfig with sensible defaults for Daytona sandbox execution."""
    return SecurityConfig()
