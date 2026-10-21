"""Run with Python 3.11+: python3 -m unittest discover -s tests -v."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".codex/hooks/subagents.py"
BRIEF = {
    "objective": "Fix the parser regression.",
    "context": "The parser currently rejects empty lists.",
    "instructions": "Read local instructions; preserve unrelated changes.",
    "allowed_files": ["src/parser.py", "tests/test_parser.py"],
    "mutable_resources": [],
    "dependencies": [],
    "acceptance": ["Empty lists parse without changing other input handling."],
    "checks": ["python3 -m unittest discover -s tests"],
    "read_only": False,
    "budget": {"minutes": 15, "attempts": 2},
}
REPORT = {
    "status": "done",
    "summary": "The parser now accepts empty lists.",
    "changed_files": ["src/parser.py", "tests/test_parser.py"],
    "checks": ["python3 -m unittest discover -s tests: exit 0, 4 passed"],
    "risks": [], "blockers": [], "next_action": "Coordinator reviews the diff.",
}


def fenced(tag, value):
    return f"```{tag}\n{json.dumps(value)}\n```"


def event(name="PreToolUse", **updates):
    data = {"hook_event_name": name, "cwd": "/fixture", "model": "unchanged",
            "permission_mode": "default", "session_id": "fixture-session",
            "transcript_path": None, "turn_id": "fixture-turn"}
    if name == "PreToolUse":
        data.update(tool_name="spawn_agent", tool_use_id="fixture-tool",
                    tool_input={"task_name": "parser_fix", "message": "PRIVATE_SENTINEL opaque payload"})
    else:
        data.update(agent_id="fixture-agent", agent_type="default")
    if name == "SubagentStop":
        data.update(agent_transcript_path=None, stop_hook_active=False,
                    last_assistant_message=fenced("delegation-report", REPORT))
    data.update(updates)
    return data


class GuardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name)
        self.script = self.project / ".codex/hooks/subagents.py"
        self.script.parent.mkdir(parents=True)
        shutil.copyfile(SCRIPT, self.script)
        self.working = self.project / "nested"
        self.working.mkdir()
        self.records = self.project / ".codex-delegations"
        self.records.mkdir()
        self.record = self.records / "parser_fix.json"
        self.write_brief(BRIEF)

    def write_brief(self, value):
        self.record.write_bytes(value if isinstance(value, bytes) else json.dumps(value).encode())

    def run_hook(self, data, configured="PreToolUse"):
        raw = data if isinstance(data, bytes) else json.dumps(data).encode()
        result = subprocess.run([sys.executable, str(self.script), configured],
                                input=raw, capture_output=True, timeout=3, cwd=self.working)
        self.assertEqual(result.returncode, 0, "hook must emit supported JSON decisions")
        self.assertEqual(result.stderr, b"", "hook must not log raw input/errors")
        return json.loads(result.stdout)

    def deny(self, data):
        output = self.run_hook(data)
        self.assertIn("hookSpecificOutput", output, "invalid spawn must receive a denial")
        self.assertEqual(output["hookSpecificOutput"]["hookEventName"], "PreToolUse")
        self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertNotIn("PRIVATE_SENTINEL", json.dumps(output))

    def test_missing_brief_is_denied(self):
        self.record.unlink()
        self.deny(event())

    def test_task_name_is_required_and_path_traversal_is_denied(self):
        for task_name in (None, "", "../parser_fix", "/parser_fix", "ParserFix", "a-b",
                          "a.b", "a/b", "a\\b", "a" * 65, [], False, 1, "parser_fix\n"):
            with self.subTest(task_name=task_name):
                data = event(tool_input={"task_name": task_name, "message": "PRIVATE_SENTINEL"})
                self.deny(data)
        output = self.run_hook(event(tool_input={"message": "PRIVATE_SENTINEL"}))
        reason = output["hookSpecificOutput"]["permissionDecisionReason"]
        self.assertIn("unsupported", reason)
        self.assertIn("task_name", reason)

    def test_symlinks_and_non_regular_records_are_denied_without_hanging(self):
        target = self.project / "outside.json"
        target.write_text(json.dumps(BRIEF))
        self.record.unlink()
        self.record.symlink_to(target)
        self.deny(event())
        self.record.unlink()
        self.record.mkdir()
        self.deny(event())
        self.record.rmdir()
        os.mkfifo(self.record)
        self.deny(event())
        self.record.unlink()
        self.records.rmdir()
        external = self.project / "external"
        external.mkdir()
        (external / "parser_fix.json").write_text(json.dumps(BRIEF))
        self.records.symlink_to(external, target_is_directory=True)
        self.deny(event())

    def test_sidecar_bounds_strict_json_and_script_own_project_root(self):
        valid = json.dumps(BRIEF).encode()
        self.write_brief(valid + b" " * (128 * 1024 - len(valid)))
        self.assertEqual(self.run_hook(event(cwd="/unrelated/project")), {})
        self.write_brief(valid + b" " * (128 * 1024 + 1 - len(valid)))
        self.deny(event())
        for raw in (b"[]", b"null", b"false", b"{broken PRIVATE_SENTINEL}", b"\xff",
                    b"[" * 2000 + b"]" * 2000,
                    valid.replace(b'"read_only": false', b'"read_only": false, "read_only": true'),
                    valid.replace(b'"minutes": 15', b'"minutes": NaN'),
                    fenced("delegation-brief", BRIEF).encode()):
            with self.subTest(raw=raw[:30]):
                self.write_brief(raw)
                self.deny(event())

    def test_valid_writer_and_reader_do_not_rewrite_native_input(self):
        self.assertEqual(self.run_hook(event()), {})
        before = self.record.read_bytes()
        for message in ("PRIVATE_SENTINEL opaque payload", "arbitrary payload", None, ["opaque"]):
            self.assertEqual(self.run_hook(event(tool_input={"task_name": "parser_fix",
                                                           "message": message,
                                                           "model": "untouched"})), {})
        self.assertEqual(self.record.read_bytes(), before)
        self.write_brief(dict(BRIEF, read_only=True, allowed_files=[], mutable_resources=[]))
        self.assertEqual(self.run_hook(event()), {})

    def test_matching_aliases_and_unrelated_tools(self):
        self.assertTrue((ROOT / ".codex/hooks.json").exists(), "hook configuration is required")
        config = json.loads((ROOT / ".codex/hooks.json").read_text())
        matcher = config["hooks"]["PreToolUse"][0]["matcher"]
        for name in ("spawn_agent", "Agent", "collaboration.spawn_agent",
                     "collaborationspawn_agent", "multi_agent_v1spawn_agent", "multi_agent_v2spawn_agent"):
            with self.subTest(name=name):
                self.assertIsNotNone(re.search(matcher, name))
                self.deny(event(tool_name=name, tool_input={}))
        for name in ("Bash", "send_message", "AgentExtra", "spawn_agent_extra"):
            with self.subTest(name=name):
                self.assertIsNone(re.search(matcher, name))
                self.assertEqual(self.run_hook(event(tool_name=name, tool_input=None)), {})

    def test_non_native_spawn_suffix_tools_are_not_intercepted(self):
        config = json.loads((ROOT / ".codex/hooks.json").read_text())
        matcher = config["hooks"]["PreToolUse"][0]["matcher"]
        for name in ("mcp__remote__spawn_agent", "respawn_agent", "arbitrary.spawn_agent",
                     "multi_agent_v2.spawn_agent", "collaboration.spawn_agent_extra"):
            with self.subTest(name=name, path="matcher"):
                self.assertIsNone(re.search(matcher, name))
            with self.subTest(name=name, path="handler"):
                self.assertEqual(self.run_hook(event(tool_name=name, tool_input=None)), {})

    def test_contracts_in_outer_markdown_fences_are_examples(self):
        report = fenced("delegation-report", REPORT)
        for opening, closing in (("~~~text", "~~~"), ("~~~~text", "~~~~"),
                                 ("````text", "````"), ("`````", "`````"),
                                 ("   ~~~~text", "  ~~~~~  ")):
            example_report = opening + "\n" + report + "\n" + closing
            with self.subTest(opening=opening, event="SubagentStop"):
                output = self.run_hook(event("SubagentStop", last_assistant_message=example_report),
                                       "SubagentStop")
                self.assertEqual(output.get("decision"), "block")
            with self.subTest(opening=opening, event="active-contract-after-example"):
                self.assertEqual(self.run_hook(event("SubagentStop", last_assistant_message=
                    example_report + "\n" + report), "SubagentStop"), {})

    def test_denial_points_to_installed_contract(self):
        output = self.run_hook(event(tool_input={}))
        self.assertIn(".codex/delegation-brief.md",
                      output["hookSpecificOutput"]["permissionDecisionReason"])

    def test_minimal_lifecycle_payloads_do_not_require_full_envelope_validation(self):
        start = self.run_hook({"hook_event_name": "SubagentStart"}, "SubagentStart")
        self.assertIn("additionalContext", start["hookSpecificOutput"])
        stop = self.run_hook({"hook_event_name": "SubagentStop", "stop_hook_active": False},
                             "SubagentStop")
        self.assertEqual(stop["decision"], "block")
        for configured in ("SubagentStart", "SubagentStop"):
            for raw in (b'{', b'[]', b'{"hook_event_name":null}'):
                self.assertEqual(self.run_hook(raw, configured), {})

    def test_brief_types_fields_and_bounds(self):
        for key, values in {
            "objective": [None, "", "  ", 1, []], "context": ["", {}],
            "instructions": [False, ""], "allowed_files": ["a.py", [""], [1]],
            "mutable_resources": [None, [False]], "dependencies": [[{}], "none"],
            "acceptance": [[], [""]], "checks": [[], [False]],
            "read_only": [0, "false", None],
            "budget": [None, {}, {"minutes": 0, "attempts": 1},
                       {"minutes": 121, "attempts": 1}, {"minutes": True, "attempts": 1},
                       {"minutes": 1, "attempts": 0}, {"minutes": 1, "attempts": 6},
                       {"minutes": 1, "attempts": 1.5},
                       {"minutes": 1, "attempts": 1, "extra": 1}],
        }.items():
            for value in values:
                with self.subTest(key=key, value=value):
                    brief = dict(BRIEF, **{key: value})
                    self.write_brief(brief)
                    self.deny(event())
        for key in BRIEF:
            brief = dict(BRIEF)
            del brief[key]
            self.write_brief(brief)
            self.deny(event())
        self.write_brief(dict(BRIEF, extra=1))
        self.deny(event())

    def test_read_only_contradictions_and_writer_without_ownership(self):
        for brief in (dict(BRIEF, read_only=True),
                      dict(BRIEF, read_only=True, allowed_files=[], mutable_resources=["port:8000"]),
                      dict(BRIEF, allowed_files=[])):
            self.write_brief(brief)
            self.deny(event())

    def test_fake_report_fences_duplicate_blocks_and_bad_json(self):
        good = fenced("delegation-report", REPORT)
        for message in ("prefix " + good, "> " + good.replace("\n", "\n> "),
                        "```text\n" + good + "\n```", good + "\n" + good,
                        good.replace("```delegation-report", "```text"),
                        "```delegation-report\n{broken PRIVATE_SENTINEL}\n```",
                        "```delegation-report\n[]\n```",
                        good.replace('"status": "done"', '"status": "done", "status": "blocked"'),
                        good + " trailing"):
            with self.subTest(message=message[:40]):
                output = self.run_hook(event("SubagentStop", last_assistant_message=message),
                                       "SubagentStop")
                self.assertEqual(output.get("decision"), "block")
                self.assertNotIn("PRIVATE_SENTINEL", json.dumps(output))

    def test_json_report_fence_accepts_the_same_exact_schema(self):
        for status in ("done", "blocked", "needs_context"):
            message = fenced("json", dict(REPORT, status=status))
            self.assertEqual(self.run_hook(event("SubagentStop", last_assistant_message=message),
                                           "SubagentStop"), {})
        for message in (json.dumps(REPORT), fenced("json", dict(REPORT, checks=[])),
                        fenced("json", dict(REPORT, extra=True)),
                        "```json\n{broken PRIVATE_SENTINEL}\n```"):
            output = self.run_hook(event("SubagentStop", last_assistant_message=message),
                                   "SubagentStop")
            self.assertEqual(output.get("decision"), "block")
            self.assertNotIn("PRIVATE_SENTINEL", json.dumps(output))

    def test_multiple_accepted_report_fences_are_ambiguous(self):
        custom, standard = fenced("delegation-report", REPORT), fenced("json", REPORT)
        for message in (custom + "\n" + standard, standard + "\n" + custom,
                        standard + "\n" + standard,
                        custom + "\n" + fenced("json", {})):
            output = self.run_hook(event("SubagentStop", last_assistant_message=message),
                                   "SubagentStop")
            self.assertEqual(output.get("decision"), "block")

    def test_json_report_examples_in_outer_fences_do_not_count(self):
        report = fenced("json", REPORT)
        for opening, closing in (("~~~text", "~~~"), ("````text", "````")):
            example = opening + "\n" + report + "\n" + closing
            output = self.run_hook(event("SubagentStop", last_assistant_message=example),
                                   "SubagentStop")
            self.assertEqual(output.get("decision"), "block")
            self.assertEqual(self.run_hook(event("SubagentStop", last_assistant_message=
                             example + "\n" + report), "SubagentStop"), {})

    def test_malformed_payloads_are_bounded_and_never_echoed(self):
        for raw in (b'{"PRIVATE_SENTINEL":', b'\xff', b'[]', b'null', b'false',
                    b'{' + b' ' * (128 * 1024), b'[' * 2000 + b']' * 2000,
                    b'{"hook_event_name":"PreToolUse","hook_event_name":"Other"}'):
            self.deny(raw)
        for updates in ({"tool_input": None}, {"tool_input": []},
                        {"tool_input": {}}, {"tool_input": {"task_name": []}},
                        {"tool_name": None}):
            self.deny(event(**updates))

    def test_unknown_events_and_configured_events_are_noop(self):
        self.assertEqual(self.run_hook({"hook_event_name": "Unknown"}), {})
        self.assertEqual(self.run_hook(event(), configured="Unknown"), {})

    def test_start_injects_procedure_and_report_fields_without_raw_echo(self):
        output = self.run_hook(event("SubagentStart", agent_id="PRIVATE_SENTINEL"), "SubagentStart")
        specific = output["hookSpecificOutput"]
        self.assertEqual(specific["hookEventName"], "SubagentStart")
        for field in REPORT:
            self.assertIn(field, specific["additionalContext"])
        for term in ("native task name", ".codex-delegations/", "identity", "blocked",
                     "host metadata", "/root/reader", "final component", "coordinator-supplied",
                     "one exact", "[a-z0-9_]{1,64}", "native identity binding unverified",
                     "do not fabricate", "continue authorized declared scope"):
            self.assertIn(term, specific["additionalContext"])
        self.assertNotIn("PRIVATE_SENTINEL", json.dumps(output))
        self.assertNotIn("If identity or the matching record is unavailable", specific["additionalContext"])

    def test_stop_structure_and_single_continuation(self):
        self.assertEqual(self.run_hook(event("SubagentStop"), "SubagentStop"), {})
        for message in (None, "finished", fenced("delegation-report", {}),
                        fenced("delegation-report", dict(REPORT, checks=[])),
                        fenced("delegation-report", dict(REPORT, summary=[]))):
            data = event("SubagentStop", last_assistant_message=message)
            output = self.run_hook(data, "SubagentStop")
            self.assertEqual(output["decision"], "block")
            self.assertIn("delegation-report", output["reason"])
            data["stop_hook_active"] = True
            self.assertEqual(self.run_hook(data, "SubagentStop"), {})
        for flag in (None, "false", 0):
            self.assertEqual(self.run_hook(event("SubagentStop", stop_hook_active=flag,
                                                last_assistant_message=None), "SubagentStop"), {})

    def test_blocked_reports_are_valid_but_unknown_status_is_not(self):
        for status in ("blocked", "needs_context"):
            report = dict(REPORT, status=status, blockers=["Missing fixture"],
                          next_action="Coordinator supplies fixture")
            self.assertEqual(self.run_hook(event("SubagentStop", last_assistant_message=
                                                fenced("delegation-report", report)), "SubagentStop"), {})
        data = event("SubagentStop", last_assistant_message=
                     fenced("delegation-report", dict(REPORT, status="success")))
        self.assertEqual(self.run_hook(data, "SubagentStop")["decision"], "block")

    def test_report_claims_are_not_treated_as_verified_truth(self):
        report = dict(REPORT, checks=["Invented passing result"])
        self.assertEqual(self.run_hook(event("SubagentStop", last_assistant_message=
                                            fenced("delegation-report", report)), "SubagentStop"), {})


if __name__ == "__main__":
    unittest.main()
