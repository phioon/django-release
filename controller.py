"""Bounded, fail-closed Django release orchestration; Python 3.11 stdlib only."""

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import selectors
import stat
import subprocess
import sys
import time
from urllib.parse import quote, urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener


PHASES = ("schema", "application")
RECEIPT_PREFIX = "DJANGO_RELEASE_RESULT "
FAILURE_PREFIX = "DJANGO_RELEASE_FAILURE "
FAILURE_STAGES = ("migration", "consumer-verification")
BOT = "github-actions[bot]"
UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
ROOT = Path(__file__).resolve().parent
MAX_TREE_PATHS = 50_000
MAX_TREE_BYTES = 4_000_000
TREE_READ_SECONDS = 30


class Blocked(Exception):
    """Fixed reason codes only; never include remote diagnostics or secrets."""


def require(condition, reason):
    if not condition:
        raise Blocked(reason)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate-json-key")
        result[key] = value
    return result


def decode(text):
    try:
        return json.loads(text, object_pairs_hook=unique_object,
                          parse_constant=lambda _: require(False, "invalid-json"))
    except (ValueError, TypeError):
        raise Blocked("invalid-json") from None


def validate(value, schema):
    """Execute the deliberately small JSON Schema subset used by our contracts."""
    if "anyOf" in schema:
        for alternative in schema["anyOf"]:
            try:
                validate(value, alternative)
                return
            except Blocked:
                pass
        raise Blocked("invalid-contract")
    if "const" in schema:
        require(type(value) is type(schema["const"]) and value == schema["const"],
                "unsupported-format-or-result")
    if "enum" in schema:
        require(value in schema["enum"], "invalid-contract")
    kind = schema.get("type")
    types = {"object": dict, "array": list, "string": str, "integer": int,
             "boolean": bool, "null": type(None)}
    if kind:
        require(type(value) is types[kind], "invalid-contract")
    if kind == "object":
        require(set(value) == set(schema["required"]), "unknown-or-missing-field")
        for key, child in schema["properties"].items():
            validate(value[key], child)
    elif kind == "array":
        require(len(value) <= schema["maxItems"], "contract-size-limit")
        if schema.get("uniqueItems"):
            require(len({json.dumps(v, sort_keys=True) for v in value}) == len(value),
                    "duplicate-contract-item")
        for item in value:
            validate(item, schema["items"])
    elif kind == "string":
        require(schema.get("minLength", 0) <= len(value) <= schema.get("maxLength", 10000),
                "contract-size-limit")
        require(not any(ord(char) < 32 for char in value), "invalid-contract")
        if "pattern" in schema:
            require(re.search(schema["pattern"], value), "invalid-contract")
    elif kind == "integer":
        require(value >= schema.get("minimum", 0), "invalid-contract")


def contract(value, name):
    version = value.get("format_version") if type(value) is dict else None
    require(type(version) is int and version in ((1, 2) if name == "policy" else (1,)),
            "unsupported-format-or-result")
    validate(value, decode((ROOT / "schemas" / f"{name}-v{version}.schema.json").read_text()))
    return value


def release_phases(policy):
    return ("schema",) if policy["format_version"] == 2 else PHASES


def historical_service(policy, phase):
    if phase == "application" and policy["format_version"] == 2:
        return policy["historical_application_service_id"]
    return policy[phase]["service_id"]


def load_policy(path):
    """Read an offline fixture. Runtime policy must use committed_policy instead."""
    require(path.stat().st_size <= 16384, "policy-size-limit")
    return policy_bytes(path.read_bytes())


def policy_bytes(content):
    require(len(content) <= 16384, "policy-size-limit")
    policy = contract(decode(content), "policy")
    require(policy["schema"]["service_id"] != historical_service(policy, "application"),
            "schema-application-must-be-isolated")
    require(policy["schema"]["public_http"] is False
            and policy["schema"]["restart_policy"] == "NEVER"
            and policy["schema"]["healthcheck_path"] is None,
            "schema-must-be-private-one-shot")
    require(".." not in policy["branch"] and not policy["branch"].startswith("/"),
            "invalid-branch")
    return policy


def verify_dashboard_only_tree(workspace, sha):
    """Reject Railway's default config names anywhere in the exact candidate tree.

    Stream NUL-delimited paths with byte/count/time bounds, without printing file
    names or buffering the entire repository tree. Include directory entries so
    every committed path is checked, irrespective of provider root discovery.
    """
    require(re.fullmatch(r"[0-9a-f]{40}", sha), "wrong-workflow-context")
    command = ["git", "--no-replace-objects", "--literal-pathspecs", "-C", str(workspace),
               "ls-tree", "-r", "-t", "--name-only", "-z", sha]
    process = None
    try:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                   env={**os.environ, "GIT_NO_LAZY_FETCH": "1"})
        deadline = time.monotonic() + TREE_READ_SECONDS
        byte_count, path_count, pending = 0, 0, b""
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            while True:
                remaining = deadline - time.monotonic()
                require(remaining > 0 and selector.select(remaining), "candidate-tree-time-limit")
                chunk = os.read(process.stdout.fileno(), min(65536, MAX_TREE_BYTES - byte_count + 1))
                if not chunk:
                    break
                byte_count += len(chunk)
                require(byte_count <= MAX_TREE_BYTES, "candidate-tree-size-limit")
                paths = (pending + chunk).split(b"\0")
                pending = paths.pop()
                for path in paths:
                    path_count += 1
                    require(path_count <= MAX_TREE_PATHS, "candidate-tree-path-limit")
                    require(path and path.rsplit(b"/", 1)[-1] not in (b"railway.toml", b"railway.json"),
                            "committed-railway-config-not-supported")
        require(not pending, "candidate-tree-incomplete")
        remaining = deadline - time.monotonic()
        require(remaining > 0, "candidate-tree-time-limit")
        require(process.wait(timeout=remaining) == 0, "candidate-tree-unavailable")
    except subprocess.TimeoutExpired:
        raise Blocked("candidate-tree-time-limit") from None
    except OSError:
        raise Blocked("candidate-tree-unavailable") from None
    finally:
        if process is not None:
            if process.poll() is None:
                process.kill()
            process.wait()
            process.stdout.close()


def committed_policy(workspace, relative, sha):
    """Validate file/index identity and parse only the exact committed blob bytes.

    Descriptor-relative opens refuse symlinks at every checkout path component.
    The final filesystem read is compared with the commit but never parsed, so
    later filesystem changes cannot replace the policy used for this release.
    """
    path = PurePosixPath(relative)
    require(type(relative) is str and relative and path.parts and not path.is_absolute()
            and path.as_posix() == relative and all(p not in (".", "..") for p in path.parts)
            and "\\" not in relative and not any(ord(char) < 32 for char in relative),
            "policy-path-must-be-normalized-relative")
    require(re.fullmatch(r"[0-9a-f]{40}", sha), "wrong-workflow-context")

    def git(*args):
        result = subprocess.run(["git", "--no-replace-objects", "--literal-pathspecs",
                                 "-C", str(workspace), *args],
                                capture_output=True, check=False)
        require(result.returncode == 0, "policy-git-read-failed")
        return result.stdout

    tree = git("ls-tree", "-z", sha, "--", relative).split(b"\0")
    require(len(tree) == 2 and tree[1] == b"", "policy-must-be-committed-regular-blob")
    header, separator, name = tree[0].partition(b"\t")
    fields = header.split(b" ")
    require(separator and name == relative.encode() and len(fields) == 3
            and fields[0] in (b"100644", b"100755") and fields[1] == b"blob",
            "policy-must-be-committed-regular-blob")
    mode, _, object_id = fields
    require(re.fullmatch(rb"[0-9a-f]{40}", object_id), "invalid-policy-blob")
    index = git("ls-files", "--stage", "-z", "--", relative)
    require(index == mode + b" " + object_id + b" 0\t" + name + b"\0",
            "policy-index-must-match-commit")
    size = git("cat-file", "-s", object_id.decode()).strip()
    require(size.isdigit() and int(size) <= 16384, "policy-size-limit")
    content = git("cat-file", "blob", object_id.decode())
    require(len(content) == int(size), "invalid-policy-blob")

    directory = None
    try:
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        directory = os.open(workspace, flags)
        for component in path.parts[:-1]:
            child = os.open(component, flags, dir_fd=directory)
            os.close(directory)
            directory = child
        descriptor = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                             dir_fd=directory)
        with os.fdopen(descriptor, "rb") as file:
            info = os.fstat(file.fileno())
            require(stat.S_ISREG(info.st_mode), "policy-must-be-regular-file")
            require(bool(info.st_mode & 0o111) == (mode == b"100755"),
                    "policy-checkout-must-match-commit")
            require(file.read(16385) == content, "policy-checkout-must-match-commit")
    except OSError:
        raise Blocked("policy-path-missing-or-symlink") from None
    finally:
        if directory is not None:
            os.close(directory)
    return policy_bytes(content)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise Blocked("remote-redirect-refused")


def request(url, token, *, data=None, railway=False):
    headers = {"Accept": "application/json", "Content-Type": "application/json",
               "User-Agent": "django-release-v1", "X-GitHub-Api-Version": "2022-11-28"}
    headers["Project-Access-Token" if railway else "Authorization"] = (
        token if railway else "Bearer " + token)
    try:
        # A failed response may hide a successful mutation. Never retry requests.
        with build_opener(NoRedirect()).open(Request(
                url, headers=headers,
                data=None if data is None else json.dumps(data).encode()), timeout=30) as response:
            remaining = response.headers.get("X-RateLimit-Remaining")
            require(remaining is None or int(remaining) > 0, "rate-allowance-exhausted")
            body = response.read(4_000_001)
            require(len(body) <= 4_000_000, "remote-response-size-limit")
            return decode(body)
    except Blocked:
        raise
    except Exception:
        raise Blocked("remote-response-unknown") from None


class GitHub:
    def __init__(self, policy, token):
        self.policy, self.token = policy, token
        self.base = "https://api.github.com/repos/" + policy["repository"]

    def api(self, path, data=None):
        return request(self.base + path, self.token, data=data)

    def head(self):
        return self.api("/git/ref/heads/" + quote(self.policy["branch"], safe=""))["object"]["sha"]

    def category(self, phase):
        return self.policy["consumer"] + "-release-" + phase

    def lookup(self, phase, sha=None):
        query = {"environment": self.category(phase), "per_page": 2}
        if sha:
            query["sha"] = sha
        rows = self.api("/deployments?" + urlencode(query))
        require(type(rows) is list and len(rows) <= 2, "invalid-history-page")
        require(len({r["id"] for r in rows}) == len(rows), "duplicate-release-record")
        for item in rows:
            self.validate_record(item)
            require(item["payload"]["phase"] == phase, "wrong-record-category")
            if sha:
                require(item["sha"] == sha, "wrong-record-sha")
        require(all(rows[i]["id"] > rows[i + 1]["id"] for i in range(len(rows) - 1)),
                "unordered-history-page")
        return rows

    def get(self, number):
        item = self.api("/deployments/" + str(number))
        require(item["id"] == number, "wrong-record-id")
        self.validate_record(item)
        return item

    def validate_record(self, item):
        p = contract(item["payload"], "record")
        require(type(item["id"]) is int and item["id"] > 0, "wrong-record-id")
        require(item["creator"]["login"] == BOT, "untrusted-record-creator")
        require(item["sha"] == p["source_sha"]
                and item["environment"] == self.category(p["phase"]), "wrong-record-binding")
        for key in ("repository", "consumer", "workflow", "project_id", "environment_id"):
            require(p[key] == self.policy[key], "wrong-record-target")
        require(p["service_id"] == historical_service(self.policy, p["phase"]), "wrong-record-target")
        require(all(v is None or v < item["id"] for v in p["previous_heads"].values()),
                "broken-history-continuity")
        if p["phase"] == "application":
            require(p["previous_heads"]["schema"] is not None, "schema-predecessor-not-verified")

    def validate_run(self, sha, run_id, attempt):
        run = self.api(f"/actions/runs/{run_id}/attempts/{attempt}")
        require(run["id"] == run_id and run["run_attempt"] == attempt
                and run["head_sha"] == sha and run["event"] == "push"
                and run["head_branch"] == self.policy["branch"]
                and run["path"] == self.policy["workflow"]
                and run["repository"]["full_name"] == self.policy["repository"]
                and run["head_repository"]["full_name"] == self.policy["repository"],
                "unbound-workflow-run")

    def status(self, item):
        # At most submission plus terminal status. Repeated identical statuses
        # from interrupted writes are harmless, but all observed data is bounded.
        rows = self.api(f"/deployments/{item['id']}/statuses?per_page=20")
        require(type(rows) is list and len(rows) < 20, "status-history-limit")
        if not rows:
            return ("intent", None)
        allowed = {"submitted": "in_progress", "verified": "success",
                   "failed": "failure", "stale": "failure"}
        states = []
        for row in reversed(rows):
            require(row["creator"]["login"] == BOT, "untrusted-record-status")
            expected_url = ("https://github.com/" + self.policy["repository"]
                            + "/actions/runs/" + str(item["payload"]["run_id"]))
            require(row["log_url"] == expected_url, "unbound-record-status")
            parts = row["description"].split(":")
            require(len(parts) == 3 and parts[0] == "v1" and parts[1] in allowed,
                    "unsupported-status-format")
            state, deployment = parts[1:]
            require(row["state"] == allowed[state], "contradictory-record-status")
            require((state == "stale" and deployment == "none")
                    or (state != "stale" and re.fullmatch(UUID, deployment)),
                    "invalid-status-deployment")
            current = (state, None if deployment == "none" else deployment)
            if states:
                previous = states[-1]
                require(current == previous or (previous[0] == "submitted"
                        and state in ("verified", "failed") and deployment == previous[1]),
                        "contradictory-record-status")
            else:
                require(state in ("submitted", "stale"), "missing-submission-status")
            states.append(current)
        return states[-1]

    def snapshot(self, sha):
        """Read active heads plus their immediate verified checkpoints.

        Terminal records certify their already-checked ancestry. Never rescan
        every historical Actions run. Two newest rows expose a skipped head;
        SHA lookup detects duplicate/replayed historical candidates.
        """
        rows, heads, cache = {}, {}, {}
        pages = {phase: self.lookup(phase) for phase in PHASES}
        for phase, page in pages.items():
            heads[phase] = page[0]["id"] if page else None
            if page:
                require(page[0]["payload"]["previous_heads"][phase]
                        == (page[1]["id"] if len(page) > 1 else None),
                        "broken-history-continuity")
            for item in page:
                rows[item["id"]] = item
            candidates = self.lookup(phase, sha)
            require(len(candidates) <= 1, "duplicate-release-intents")
            for item in candidates:
                rows[item["id"]] = item
        for page in pages.values():
            if not page:
                continue
            for phase, number in page[0]["payload"]["previous_heads"].items():
                if number is None:
                    continue
                predecessor = rows.get(number) or self.get(number)
                require(predecessor["payload"]["phase"] == phase, "broken-history-continuity")
                rows[number] = predecessor
                state = cache.get(number)
                if state is None:
                    state = self.status(predecessor)
                    cache[number] = state
                require(state[0] in ("verified", "failed", "stale"), "prior-release-unresolved")
        for item in list(rows.values()):
            if item["payload"]["phase"] != "application":
                continue
            number = item["payload"]["previous_heads"]["schema"]
            predecessor = rows.get(number) or self.get(number)
            require(predecessor["payload"]["phase"] == "schema"
                    and predecessor["sha"] == item["sha"]
                    and predecessor["payload"]["policy_sha256"] == item["payload"]["policy_sha256"],
                    "schema-predecessor-binding-mismatch")
            rows[number] = predecessor
            state = cache.get(number)
            if state is None:
                state = self.status(predecessor)
                cache[number] = state
            require(state[0] == "verified", "schema-predecessor-not-verified")
        for item in rows.values():
            state = cache.get(item["id"])
            if state is None:
                state = self.status(item)
                cache[item["id"]] = state
            if state[0] not in ("verified", "failed", "stale"):
                p = item["payload"]
                self.validate_run(p["source_sha"], p["run_id"], p["run_attempt"])
                require(p["phase"] in release_phases(self.policy), "prior-release-unresolved")
                require(item["sha"] == sha, "prior-release-unresolved")
        return list(rows.values()), heads, cache

    def create(self, payload):
        item = self.api("/deployments", {
            "ref": payload["source_sha"], "auto_merge": False, "required_contexts": [],
            "environment": self.category(payload["phase"]),
            "description": "Django release v1 submission intent", "payload": payload,
            "transient_environment": False, "production_environment": True})
        self.validate_record(item)
        require(item["payload"] == payload, "created-record-mismatch")
        return item

    def record(self, item, state, deployment):
        self.api(f"/deployments/{item['id']}/statuses", {
            "state": {"submitted": "in_progress", "verified": "success",
                      "failed": "failure", "stale": "failure"}[state],
            "description": f"v1:{state}:{deployment or 'none'}", "auto_inactive": False,
            "log_url": "https://github.com/" + self.policy["repository"]
                       + "/actions/runs/" + str(item["payload"]["run_id"])})
        require(self.status(item) == (state, deployment), "status-write-unconfirmed")


class Railway:
    def __init__(self, policy, token):
        self.policy, self.token = policy, token

    def query(self, query, variables):
        result = request("https://backboard.railway.com/graphql/v2", self.token,
                         data={"query": query, "variables": variables}, railway=True)
        require(type(result) is dict and not result.get("errors")
                and type(result.get("data")) is dict, "provider-response-unknown")
        return result["data"]

    def target(self, service):
        return {"projectId": self.policy["project_id"],
                "environmentId": self.policy["environment_id"], "serviceId": service}

    def preflight(self, phase):
        service = self.policy[phase]
        result = self.query("""query($projectId:String!,$environmentId:String!,$serviceId:String!){
          service(id:$serviceId){id name projectId}
          tcpProxies(environmentId:$environmentId,serviceId:$serviceId){id}
          serviceInstanceAutoDeployStatus(projectId:$projectId,environmentId:$environmentId,serviceId:$serviceId){enabled}
          serviceInstance(environmentId:$environmentId,serviceId:$serviceId){serviceId environmentId
            source{repo image} railwayConfigFile rootDirectory preDeployCommand startCommand
            healthcheckPath numReplicas restartPolicyType domains{serviceDomains{id} customDomains{id}}}
        }""", self.target(service["service_id"]))
        instance = result["serviceInstance"]
        config_binding = instance["railwayConfigFile"]
        require(result["service"] == {"id": service["service_id"], "name": service["name"],
                                      "projectId": self.policy["project_id"]}
                and instance["serviceId"] == service["service_id"]
                and instance["environmentId"] == self.policy["environment_id"],
                "wrong-provider-target")
        require(result["serviceInstanceAutoDeployStatus"]["enabled"] is False,
                "native-autodeploy-must-be-disabled")
        require(instance["source"] == {"repo": self.policy["repository"], "image": None}
                and (config_binding is None or type(config_binding) is str and config_binding == "")
                and service["config"] is None
                and (instance["rootDirectory"] or "/") == service["root_directory"]
                and not instance["preDeployCommand"] and instance["numReplicas"] == 1
                and not result["tcpProxies"], "provider-service-config-drift")
        if not service["public_http"]:
            require(not instance["domains"]["serviceDomains"]
                    and not instance["domains"]["customDomains"], "unexpected-public-domain")
        require(instance["startCommand"] == service["start_command"]
                and instance["healthcheckPath"] == service["healthcheck_path"]
                and instance["restartPolicyType"] == service["restart_policy"],
                "provider-process-config-drift")

    def deployments(self, service):
        rows, after, cursors = [], None, set()
        for _ in range(10):
            result = self.query("""query($input:DeploymentListInput!,$after:String){
              deployments(input:$input,first:100,after:$after){pageInfo{hasNextPage endCursor}
                edges{node{id projectId environmentId serviceId status meta}}}}
              """, {"input": self.target(service), "after": after})["deployments"]
            require(type(result["edges"]) is list and len(result["edges"]) <= 100,
                    "invalid-provider-page")
            rows.extend(edge["node"] for edge in result["edges"])
            require(len({row["id"] for row in rows}) == len(rows), "duplicate-provider-deployment")
            info = result["pageInfo"]
            require(type(info["hasNextPage"]) is bool, "invalid-provider-page")
            if not info["hasNextPage"]:
                return rows
            after = info["endCursor"]
            require(type(after) is str and after and after not in cursors,
                    "broken-provider-pagination")
            cursors.add(after)
        raise Blocked("provider-history-limit")

    def submit(self, service, sha):
        result = self.query("""mutation($serviceId:String!,$environmentId:String!,$commitSha:String!){
          serviceInstanceDeployV2(serviceId:$serviceId,environmentId:$environmentId,commitSha:$commitSha)}""",
                            {"serviceId": service, "environmentId": self.policy["environment_id"],
                             "commitSha": sha})
        deployment = result["serviceInstanceDeployV2"]
        require(type(deployment) is str and re.fullmatch(UUID, deployment),
                "provider-submission-unattributed")
        return deployment

    def receipt(self, deployment, expected):
        """Return verified, an enumerated failure stage, or None from bound logs."""
        rows = self.query("""query($deploymentId:String!){
          deploymentLogs(deploymentId:$deploymentId,limit:500){message}}""",
                          {"deploymentId": deployment})["deploymentLogs"]
        require(type(rows) is list and len(rows) < 500, "receipt-log-window-incomplete")
        matches = []
        for row in rows:
            message = row["message"]
            require(type(message) is str, "invalid-provider-log")
            for prefix, name in ((RECEIPT_PREFIX, "receipt"), (FAILURE_PREFIX, "failure")):
                if message.startswith(prefix):
                    require(len(message) <= 4096, "receipt-size-limit")
                    matches.append((name, contract(decode(message[len(prefix):]), name)))
        require(len(matches) <= 1, "duplicate-maintenance-receipt")
        if matches:
            name, result = matches[0]
            if name == "failure":
                identity = {k: v for k, v in expected.items()
                            if k not in ("migrations_verified", "acl_verified", "acl_policy")}
                require(result == {**identity, "stage": result["stage"]}, "wrong-maintenance-receipt")
                return result["stage"]
            require(result == expected, "wrong-maintenance-receipt")
            return "verified"
        return None


class Engine:
    def __init__(self, policy, github, railway, sha, run_id, run_attempt,
                 *, sleep=time.sleep, polls=240):
        self.policy, self.github, self.railway = policy, github, railway
        self.sha, self.run_id, self.run_attempt = sha, run_id, run_attempt
        self.sleep, self.polls = sleep, polls
        self.policy_hash = hashlib.sha256(json.dumps(
            policy, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    def current(self):
        require(self.github.head() == self.sha, "stale-candidate")

    def bound_deployments(self, service):
        rows = self.railway.deployments(service)
        for row in rows:
            require((row["projectId"], row["environmentId"], row["serviceId"]) ==
                    (self.policy["project_id"], self.policy["environment_id"], service),
                    "wrong-deployment-target")
            require(type(row["id"]) is str and re.fullmatch(UUID, row["id"]),
                    "invalid-deployment-id")
        require(len({r["id"] for r in rows}) == len(rows), "duplicate-provider-deployment")
        return rows

    def phase(self, phase):
        rows, heads, states = self.github.snapshot(self.sha)
        existing = [r for r in rows if r["sha"] == self.sha and r["payload"]["phase"] == phase]
        require(len(existing) <= 1, "duplicate-release-intents")
        service = self.policy[phase]["service_id"]
        if existing:
            item = existing[0]
            require(item["payload"]["policy_sha256"] == self.policy_hash, "release-policy-changed")
            state, submitted = states[item["id"]]
            require(state not in ("failed", "stale"), phase + "-forward-recovery-required")
            if state == "verified":
                return
            require(state == "submitted", phase + "-submission-unattributed-no-resubmit")
        else:
            self.current()
            for target_phase in release_phases(self.policy):
                self.railway.preflight(target_phase)
            before = self.bound_deployments(service)
            require(not any(r.get("meta", {}).get("commitHash") == self.sha for r in before),
                    "untracked-same-sha-deployment")
            require(all(r["status"] in ("SUCCESS", "FAILED", "CRASHED", "REMOVED", "SKIPPED")
                        for r in before), "provider-deployment-still-active")
            if phase == "application":
                schema = [r for r in rows if r["sha"] == self.sha
                          and r["payload"]["phase"] == "schema"]
                require(len(schema) == 1 and states[schema[0]["id"]][0] == "verified"
                        and heads["schema"] == schema[0]["id"], "schema-predecessor-not-verified")
            self.current()
            payload = {"format_version": 1, "repository": self.policy["repository"],
                       "consumer": self.policy["consumer"], "phase": phase, "source_sha": self.sha,
                       "workflow": self.policy["workflow"], "run_id": self.run_id,
                       "run_attempt": self.run_attempt, "project_id": self.policy["project_id"],
                       "environment_id": self.policy["environment_id"], "service_id": service,
                       "policy_sha256": self.policy_hash, "before": [r["id"] for r in before],
                       "previous_heads": heads}
            contract(payload, "record")
            item = self.github.create(payload)
            # Re-read after creating the durable intent. Concurrent writers or
            # broken checkpoint continuity stop here, before provider mutation.
            _, observed_heads, _ = self.github.snapshot(self.sha)
            require(observed_heads == {**heads, phase: item["id"]}, "release-owner-changed")
            if self.github.head() != self.sha:
                self.github.record(item, "stale", None)
                raise Blocked("stale-candidate")
            submitted = self.railway.submit(service, self.sha)
            # Lost response, malformed ID, or failed durable write leaves the
            # intent unresolved. No discovery by timing, SHA or matching image.
            self.github.record(item, "submitted", submitted)
        before = set(item["payload"]["before"])
        expected = {"format_version": 1, "repository": self.policy["repository"],
                    "consumer": self.policy["consumer"], "source_sha": self.sha,
                    "project_id": self.policy["project_id"],
                    "environment_id": self.policy["environment_id"], "service_id": service,
                    "deployment_id": submitted, "migrations_verified": True,
                    "acl_verified": True, "acl_policy": self.policy["acl_policy"]}
        for _ in range(self.polls):
            candidates = [r for r in self.bound_deployments(service) if r["id"] not in before]
            exact = [r for r in candidates if r["id"] == submitted]
            if exact:
                row = exact[0]
                require(row.get("meta", {}).get("commitHash") == self.sha,
                        "provider-deployment-binding-mismatch")
                if row["status"] in ("FAILED", "CRASHED", "SKIPPED"):
                    self.github.record(item, "failed", submitted)
                    # Conclusive provider failure is durable before optional
                    # stage diagnostics; missing/unreadable logs cannot undo it.
                    if phase == "schema":
                        try:
                            result = self.railway.receipt(submitted, expected)
                        except Exception:
                            result = None
                        if result in FAILURE_STAGES:
                            raise Blocked("schema-" + result + "-failed-forward-recovery-required")
                    raise Blocked(phase + "-forward-recovery-required")
                verified = row["status"] == "SUCCESS"
                if phase == "schema":
                    result = self.railway.receipt(submitted, expected)
                    if result in FAILURE_STAGES:
                        self.github.record(item, "failed", submitted)
                        raise Blocked("schema-" + result + "-failed-forward-recovery-required")
                    verified = row["status"] in ("SUCCESS", "REMOVED") and result == "verified"
                if verified:
                    require(len(candidates) == 1, "ambiguous-provider-submission")
                    self.github.record(item, "verified", submitted)
                    return
            self.sleep(5)
        raise Blocked(phase + "-observation-unresolved-no-resubmit")

    def execute(self):
        self.github.validate_run(self.sha, self.run_id, self.run_attempt)
        for phase in release_phases(self.policy):
            self.phase(phase)


def context(policy, env):
    require(env.get("GITHUB_EVENT_NAME") == "push"
            and env.get("GITHUB_REPOSITORY") == policy["repository"]
            and env.get("GITHUB_REF") == "refs/heads/" + policy["branch"]
            and env.get("GITHUB_WORKFLOW_REF") == (policy["repository"] + "/" + policy["workflow"]
                                                   + "@refs/heads/" + policy["branch"])
            and re.fullmatch(r"[0-9a-f]{40}", env.get("GITHUB_SHA", ""))
            and re.fullmatch(r"[1-9][0-9]*", env.get("GITHUB_RUN_ID", ""))
            and re.fullmatch(r"[1-9][0-9]*", env.get("GITHUB_RUN_ATTEMPT", "")),
            "wrong-workflow-context")
    event_path = Path(env["GITHUB_EVENT_PATH"])
    require(event_path.stat().st_size <= 4_000_000, "event-size-limit")
    event = decode(event_path.read_text())
    require(event["after"] == env["GITHUB_SHA"] and event.get("deleted") is False
            and event["ref"] == env["GITHUB_REF"]
            and event["repository"]["full_name"] == policy["repository"], "wrong-push-event")
    result = subprocess.run(["git", "-C", env["GITHUB_WORKSPACE"], "rev-parse", "HEAD"],
                            capture_output=True, text=True, check=False)
    require(result.returncode == 0 and result.stdout.strip() == env["GITHUB_SHA"],
            "checkout-must-match-event-sha")


def main():
    try:
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument("--policy", required=True)
        args = parser.parse_args()
        require(sys.version_info[:2] == (3, 11), "python-311-required")
        env = os.environ
        workspace = Path(env["GITHUB_WORKSPACE"])
        verify_dashboard_only_tree(workspace, env.get("GITHUB_SHA", ""))
        policy = committed_policy(workspace, args.policy, env.get("GITHUB_SHA", ""))
        context(policy, env)
        require(env.get("GITHUB_TOKEN") and env.get("RAILWAY_TOKEN"), "release-credentials-unconfigured")
        Engine(policy, GitHub(policy, env["GITHUB_TOKEN"]), Railway(policy, env["RAILWAY_TOKEN"]),
               env["GITHUB_SHA"], int(env["GITHUB_RUN_ID"]), int(env["GITHUB_RUN_ATTEMPT"])).execute()
        phases = "schema" if policy["format_version"] == 2 else "schema and application"
        print(f"django-release: {phases} records verified; check serving readiness separately")
        return 0
    except Blocked as error:
        print("django-release blocked: " + str(error)
              + ". Preserve release records; see docs/security-recovery.md before retrying.")
        return 1
    except Exception:
        print("django-release blocked: invalid-or-unavailable-response. Details suppressed; "
              "preserve records and inspect access/configuration privately.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
