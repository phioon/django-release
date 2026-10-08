"""Offline, dependency-free repository contract and syntax checks."""

import ast
import importlib.util
import json
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
ACTION_PINS = {
    "checkout": "3d3c42e5aac5ba805825da76410c181273ba90b1",
    "setup-python": "5fda3b95a4ea91299a34e894583c3862153e4b97",
}
sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location("release_controller", ROOT / "controller.py")
controller = importlib.util.module_from_spec(spec)
spec.loader.exec_module(controller)


def main():
    assert sys.version_info[:2] == (3, 11), "Use Python 3.11"
    for path in ROOT.rglob("*.py"):
        ast.parse(path.read_text(), filename=str(path))
    for path in ROOT.rglob("*.json"):
        controller.decode(path.read_text())
    for path in (ROOT / "tests/fixtures").glob("*.json"):
        controller.load_policy(path)
    expected = {"version": 1, "profile": "django-release-python311-v1"}
    assert json.loads((ROOT / ".github/local-checks.json").read_text()) == expected
    protection = json.loads((ROOT / ".github/main-protection.json").read_text())
    assert set(protection) == {"required_status_checks", "enforce_admins",
                              "required_pull_request_reviews", "restrictions",
                              "allow_force_pushes", "allow_deletions",
                              "required_conversation_resolution"}
    assert protection["enforce_admins"] is True
    assert protection["allow_force_pushes"] is False
    assert protection["allow_deletions"] is False
    action = (ROOT / "action.yml").read_text()
    assert "using: composite" in action and action.count("      run:") == 1
    assert '"$GITHUB_ACTION_PATH/controller.py" --policy "$RELEASE_POLICY"' in action
    assert set(re.findall(r"^  ([a-z-]+):$", action, re.M)) == {
        "policy", "github-token", "railway-token", "steps"}
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()
    assert "pull_request_target" not in workflow
    assert "python3 -B scripts/run_tests.py" in workflow, "CI must reject zero-test discovery"
    for pin in re.findall(r"uses: ([^\s]+)", workflow):
        assert re.fullmatch(r"actions/[a-z-]+@[0-9a-f]{40}", pin), pin
    for path in [ROOT / "README.md", ROOT / ".github/workflows/ci.yml", *sorted((ROOT / "docs").glob("*.md"))]:
        for action, pin in re.findall(r"actions/(checkout|setup-python)@([^\s]+)", path.read_text()):
            assert pin == ACTION_PINS[action], (str(path), action, "reviewed action pin changed")
    for action, pin in ACTION_PINS.items():
        assert f"actions/{action}@{pin}" in workflow
    for path in (ROOT / "action.yml", ROOT / ".github/workflows/ci.yml"):
        # Small formatting checks only; this is not a general YAML parser.
        assert "\t" not in path.read_text()
        assert all(len(line) - len(line.lstrip()) < 16 for line in path.read_text().splitlines())
    docs = ["README.md", "CONTRIBUTING.md", "SECURITY.md", "AGENTS.md",
            "docs/how-it-works.md", "docs/configuration.md", "docs/security-recovery.md",
            "docs/examples.md"]
    for name in docs:
        path = ROOT / name
        assert path.is_file() and path.stat().st_size > 100
        for target in re.findall(r"\]\(([^)]+)\)", path.read_text()):
            if not re.match(r"[a-z]+://", target) and not target.startswith("#"):
                assert (path.parent / target.split("#")[0]).exists(), (name, target)
    print("release contracts, Python syntax, action structure, pins, metadata, and local doc links: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
