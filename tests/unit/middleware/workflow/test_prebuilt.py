from __future__ import annotations

from pathlib import Path

from ptc_agent.agent.middleware.background_subagent.workflow.prebuilt import (
    PrebuiltWorkflowRegistry,
)


def _seed(root: Path, name: str, description: str) -> str:
    source = (
        f"export const meta = {{ name: '{name}', description: '{description}' }};\n"
        "return args;\n"
    )
    directory = root / "workflows" / name
    directory.mkdir(parents=True)
    (directory / "workflow.js").write_text(source)
    return source


def test_registry_loads_and_sorts_seed_workflows(tmp_path: Path) -> None:
    second = _seed(tmp_path, "second", "the second one")
    first = _seed(tmp_path, "first", "the first one")

    registry = PrebuiltWorkflowRegistry(tmp_path)

    assert registry.names() == ["first", "second"]
    assert registry.meta("first").description == "the first one"
    assert registry.get("second") == second
    # Flat <name>.js: mount keys share the user tier's shape so an edited
    # script lands on the name it runs under.
    assert registry.files() == {"first.js": first, "second.js": second}


def test_invalid_and_name_mismatched_seeds_are_skipped(
    tmp_path: Path, capsys
) -> None:
    syntax_dir = tmp_path / "workflows" / "syntax-bad"
    syntax_dir.mkdir(parents=True)
    (syntax_dir / "workflow.js").write_text("export const meta = {")
    mismatch_dir = tmp_path / "workflows" / "expected"
    mismatch_dir.mkdir(parents=True)
    (mismatch_dir / "workflow.js").write_text(
        "export const meta = { name: 'different', description: 'bad' };"
    )
    valid_dir = tmp_path / "workflows" / "valid"
    valid_dir.mkdir(parents=True)
    (valid_dir / "workflow.js").write_text(
        "export const meta = { name: 'valid', description: 'good' }; return 1;"
    )

    registry = PrebuiltWorkflowRegistry(tmp_path)

    assert registry.names() == ["valid"]
    assert "Skipping invalid prebuilt workflow" in capsys.readouterr().out


def test_absent_workflows_directory_is_empty(tmp_path: Path) -> None:
    registry = PrebuiltWorkflowRegistry(tmp_path)
    assert registry.names() == []
    assert registry.files() == {}
    assert registry.get("missing") is None
    assert registry.meta("missing") is None


REPO_ROOT = Path(__file__).resolve().parents[4]


def test_shipped_finance_committee_workflow_dispatches_known_roles() -> None:
    registry = PrebuiltWorkflowRegistry(REPO_ROOT)
    assert "finance_committee" in registry.names()
    assert registry.meta("finance_committee").description.startswith("财政部门会议")

    # The meeting dispatches real subagents: every agentType it names must be
    # an enabled role in the shipped registry, and every dispatch schema must
    # clear the server-side validation the live driver applies.
    from ptc_agent.agent.subagents.builtins import BUILTIN_SUBAGENTS

    source = registry.get("finance_committee")
    for role in ("accountant", "treasury", "tax-specialist", "fp-analyst", "internal-auditor"):
        assert f"'{role}'" in source
        assert role in BUILTIN_SUBAGENTS

    from src.config.models import WorkflowOrchestrationConfig
    from ptc_agent.agent.middleware.background_subagent.workflow.validation import (
        validate_dispatch,
    )

    caps = WorkflowOrchestrationConfig()
    known = sorted(BUILTIN_SUBAGENTS)
    rec = validate_dispatch(
        prompt="议题测试",
        opts={"agentType": "internal-auditor", "label": "risk gate", "phase": "risk-gate",
              "schema": {"type": "object", "required": ["verdict"],
                         "properties": {"verdict": {"type": "string",
                                                    "enum": ["approve", "reject"]}}}},
        known_subagent_types=known,
        default_subagent_type="general-purpose",
        caps=caps,
    )
    assert rec["subagent_type"] == "internal-auditor"

    # Quality gate: the meeting ends with an independent verification dispatch
    # (minutes cross-checked against the record) — the general-purpose verifier
    # must exist and its schema must pass the same live validation.
    assert "verification" in source
    assert "general-purpose" in BUILTIN_SUBAGENTS
    gate = validate_dispatch(
        prompt="核稿测试",
        opts={"agentType": "general-purpose", "label": "verification",
              "phase": "verification",
              "schema": {"type": "object", "required": ["passed", "unverified_claims"],
                         "properties": {"passed": {"type": "boolean"},
                                        "unverified_claims": {"type": "array",
                                                               "items": {"type": "string"}}}}},
        known_subagent_types=known,
        default_subagent_type="general-purpose",
        caps=caps,
    )
    assert gate["subagent_type"] == "general-purpose"

