"""Tests for the bite-check app's welcome bot (bot/welcome.py). No key, no network: GitHub's API is faked."""

import base64
import importlib.util
import json
import shutil
import subprocess
import sys
import urllib.parse
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("welcome", Path(__file__).parent.parent / "bot" / "welcome.py")
welcome = importlib.util.module_from_spec(spec)
spec.loader.exec_module(welcome)


def repo(name="ann/shop", language="Python", **kw):
    return {"full_name": name, "default_branch": "main", "language": language, **kw}


def test_link_fills_in_the_workflow_for_the_repos_language():
    link = welcome.add_link(repo(language="Go"))
    assert link.startswith("https://github.com/ann/shop/new/main?")
    q = urllib.parse.parse_qs(urllib.parse.urlsplit(link).query)
    assert q["filename"] == [".github/workflows/bite.yml"]
    body = q["value"][0]
    assert body == welcome.workflow("Go")
    assert "actions/setup-go" in body and "uses: connabyss/bite@" + welcome.VERSION in body
    assert "fetch-depth: 0" in body and "${{ github.event.pull_request.head.sha }}" in body


def test_unknown_language_gets_the_setup_note():
    assert welcome.OTHER in welcome.workflow(None)
    assert "couldn't tell how your tests run" in welcome.issue_body(repo(language="Haskell"))
    assert "actions/setup-node" in welcome.workflow("TypeScript")


def test_python_setup_never_installs_the_project_itself():
    # an installed checkout would be imported by every copy Bite makes, so no test would ever notice a change
    assert "-e ." not in welcome.workflow("Python") and "pip install ." not in welcome.workflow("Python")


def test_wanted_skips_bites_own_repo_archived_and_no_issues():
    assert welcome.wanted(repo())
    assert not welcome.wanted(repo(name=welcome.HOME))
    assert not welcome.wanted(repo(archived=True))
    assert not welcome.wanted(repo(has_issues=False))


@pytest.mark.skipif(not shutil.which("openssl"), reason="needs the openssl command")
def test_jwt_is_signed_by_the_key(tmp_path):
    key = tmp_path / "key.pem"
    subprocess.run(["openssl", "genrsa", "-out", str(key), "2048"], check=True, capture_output=True)
    pub = tmp_path / "pub.pem"
    subprocess.run(["openssl", "rsa", "-in", str(key), "-pubout", "-out", str(pub)], check=True, capture_output=True)
    jwt = welcome.app_jwt(key.read_text(), now=1000)
    head, body, sig = jwt.split(".")
    pad = lambda s: base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))
    assert json.loads(pad(body)) == {"iat": 940, "exp": 1540, "iss": welcome.APP_ID}
    (tmp_path / "sig").write_bytes(pad(sig))
    ok = subprocess.run(["openssl", "dgst", "-sha256", "-verify", str(pub), "-signature", str(tmp_path / "sig")],
                        input=f"{head}.{body}".encode(), capture_output=True)
    assert ok.returncode == 0


class FakeGitHub:
    def __init__(self, installs):
        self.installs = installs  # {install id: (login, [repos], {repo name: [issues]})}
        self.posted = []
        self.token_asks = []

    def call(self, method, path, token, data=None, scheme="Bearer"):
        if path.startswith("/app/installations/") and path.endswith("/access_tokens"):
            self.token_asks.append(data)
            return {"token": "inst-" + path.split("/")[3]}
        if method == "POST" and path.endswith("/issues"):
            self.posted.append((path, data))
            return {}
        raise AssertionError(path)

    def pages(self, path, token, key=None):
        if path == "/app/installations":
            return [{"id": i, "account": {"login": v[0]}} for i, v in self.installs.items()]
        inst = self.installs[int(token.split("-")[1])]
        if path == "/installation/repositories":
            return inst[1]
        name = path.split("/repos/")[1].split("/issues")[0]
        assert "creator=bite-check%5Bbot%5D" in path
        return inst[2].get(name, [])


def fake_run(monkeypatch, installs, dry_run=False):
    gh = FakeGitHub(installs)
    monkeypatch.setattr(welcome, "app_jwt", lambda key: "jwt")
    monkeypatch.setattr(welcome, "call", gh.call)
    monkeypatch.setattr(welcome, "pages", gh.pages)
    welcome.run("key", dry_run)
    return gh


def test_opens_one_issue_per_new_repo_with_an_issues_only_token(monkeypatch):
    gh = fake_run(monkeypatch, {
        1: ("ann", [repo("ann/shop"), repo("ann/old", archived=True), repo(welcome.HOME)], {}),
        2: ("bo", [repo("bo/app", language="Rust")], {"bo/app": [{"body": "unrelated"}]}),
    })
    assert [p for p, _ in gh.posted] == ["/repos/ann/shop/issues", "/repos/bo/app/issues"]
    assert all(d["body"].startswith(welcome.MARK) for _, d in gh.posted)
    assert gh.token_asks == [{"permissions": {"issues": "write"}}] * 2


def test_never_posts_twice_even_after_the_issue_was_closed(monkeypatch):
    gh = fake_run(monkeypatch, {1: ("ann", [repo("ann/shop")], {"ann/shop": [{"body": welcome.MARK + " closed"}]})})
    assert gh.posted == []


def test_big_installs_get_nothing(monkeypatch):
    many = [repo(f"big/r{i}") for i in range(welcome.MAX_REPOS + 1)]
    gh = fake_run(monkeypatch, {1: ("big", many, {})})
    assert gh.posted == []


def test_dry_run_posts_nothing(monkeypatch, capsys):
    gh = fake_run(monkeypatch, {1: ("ann", [repo("ann/shop")], {})}, dry_run=True)
    assert gh.posted == [] and "ann/shop: would open the welcome issue" in capsys.readouterr().out


def test_no_key_stops_with_a_plain_message(monkeypatch):
    monkeypatch.delenv("BITE_APP_KEY", raising=False)
    with pytest.raises(SystemExit, match="bot"):
        welcome.main()
