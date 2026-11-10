"""Security-property tests for the ``code_interpreter`` tool.

``code_interpreter`` runs model-written Python in a plain subprocess with the
host user's privileges. Unlike ``shell_exec`` it does not set
``requires_confirmation``, and its only guard is a substring blocklist. The
default bootstrap config enables it alongside ``web_search``, so text from
the web can steer what the model asks it to run.

Tests marked ``xfail(strict=True)`` document known gaps. They state the
property the tool should have and fail today for the recorded reason. Once
the gap is closed they XPASS, which strict mode reports as a failure, so the
marker has to be removed and the test then guards against regressions.

Every payload is harmless: it prints a marker or touches a file inside
pytest's ``tmp_path``.
"""

from __future__ import annotations

import pytest

from openjarvis.tools.code_interpreter import CodeInterpreterTool

_BLOCKLIST_GAP = (
    "code_interpreter relies on a substring blocklist that does not stop "
    "dynamic lookups or alternative APIs"
)

# Each payload reaches a capability the blocklist intends to deny
# (process execution, dynamic import, file writes) without containing any
# blocked substring verbatim.
BLOCKLIST_BYPASSES = {
    "getattr_os_system": "import os; getattr(os, 'sys' + 'tem')('echo MARKER')",
    "from_subprocess_import": ("from subprocess import run; run(['echo', 'MARKER'])"),
    "whitespace_before_attr": "import os; os .system('echo MARKER')",
    "builtins_dynamic_import": (
        "import builtins\n"
        "mod = getattr(builtins, '__imp' + 'ort__')('os')\n"
        "mod.system('echo MARKER')"
    ),
    "importlib_import_module": (
        "import importlib\nimportlib.import_module('o' + 's').system('echo MARKER')"
    ),
}


@pytest.fixture
def tool() -> CodeInterpreterTool:
    return CodeInterpreterTool(timeout=15)


# ---------------------------------------------------------------------------
# Properties that hold today (regression guards)
# ---------------------------------------------------------------------------


def test_blocked_code_is_never_executed(tool, tmp_path):
    """A blocked pattern anywhere in the code must stop the whole script."""
    marker = tmp_path / "ran.txt"
    code = (
        f"import pathlib\npathlib.Path({str(marker)!r}).write_text('ran')\n"
        "# os.system is mentioned here, so the script must be rejected\n"
    )
    result = tool.execute(code=code)
    assert result.success is False
    assert "Blocked" in result.content
    assert not marker.exists()


def test_timeout_reports_failure_without_returncode(tool):
    short = CodeInterpreterTool(timeout=1)
    result = short.execute(code="while True:\n    pass")
    assert result.success is False
    assert "timed out" in result.content
    assert "returncode" not in result.metadata


def test_non_string_code_is_rejected_cleanly(tool):
    """A malformed tool call from the model must not crash the agent loop."""
    result = tool.execute(code=["print(1)"])
    assert result.success is False


# ---------------------------------------------------------------------------
# Known gaps (strict xfail)
# ---------------------------------------------------------------------------


@pytest.mark.xfail(strict=True, raises=AssertionError, reason=_BLOCKLIST_GAP)
@pytest.mark.parametrize(
    "payload", BLOCKLIST_BYPASSES.values(), ids=BLOCKLIST_BYPASSES.keys()
)
def test_process_execution_bypasses_are_blocked(tool, payload):
    result = tool.execute(code=payload)
    assert "MARKER" not in result.content
    assert result.success is False


@pytest.mark.xfail(strict=True, raises=AssertionError, reason=_BLOCKLIST_GAP)
def test_filesystem_writes_without_open_are_blocked(tool, tmp_path):
    target = tmp_path / "written.txt"
    result = tool.execute(
        code=f"import pathlib\npathlib.Path({str(target)!r}).write_text('x')"
    )
    assert not target.exists()
    assert result.success is False


@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason="code_interpreter runs arbitrary code but does not require "
    "confirmation, unlike shell_exec and git tools",
)
def test_requires_confirmation_like_shell_exec(tool):
    from openjarvis.tools.shell_exec import ShellExecTool

    assert ShellExecTool().spec.requires_confirmation is True
    assert tool.spec.requires_confirmation is True


@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason="the subprocess inherits the full parent environment, "
    "including provider API keys",
)
def test_parent_secrets_are_not_inherited(tool, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-not-a-real-key")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key")
    result = tool.execute(
        code=(
            "import os\n"
            "print(os.environ.get('ANTHROPIC_API_KEY'), "
            "os.environ.get('OPENAI_API_KEY'))"
        )
    )
    assert result.success is True
    assert "sk-test-not-a-real-key" not in result.content
