import json
import time

import pytest
from click.testing import CliRunner

from instapaper_cli import client
from instapaper_cli.cli import cli

pytestmark = pytest.mark.skipif(not (client.load().get("token")), reason="not signed in: run `instapaper login`")


def run(*args):
    r = CliRunner().invoke(cli, list(args))
    assert r.exit_code == 0, r.output
    return json.loads(r.output) if r.output.lstrip().startswith(("[", "{")) else r.output


def test_bookmark_lifecycle():
    marker = f"instapaper-cli-test-{int(time.time())}"
    b = run("add", f"https://en.wikipedia.org/wiki/Instapaper?{marker}", "--title", marker, "--tag", "instapaper-cli-test")
    bid = str(b["id"])
    try:
        assert b["tags"] == ["instapaper-cli-test"] and not b["archived"]
        assert [x["id"] for x in run("list", "-n", "50", "-m", marker)] == [b["id"]]
        assert [x["id"] for x in run("list", "-t", "instapaper-cli-test")] == [b["id"]]
        assert "Instapaper" in run("text", bid)
        assert run("like", bid)[0]["liked"]
        assert b["id"] in [x["id"] for x in run("list", "-f", "liked", "-n", "50")]
        assert not run("unlike", bid)[0]["liked"]
        assert run("update", bid, "--progress", "0.5", "--description", "edited")[0]["progress"] == 0.5
        assert run("tag", bid, "--add", "instapaper-cli-test-2", "--remove", "instapaper-cli-test") == {bid: ["instapaper-cli-test-2"]}
        assert run("archive", bid)[0]["archived"]
        assert b["id"] in [x["id"] for x in run("list", "-f", "archive", "-n", "50")]
        assert not run("unarchive", bid)[0]["archived"]
    finally:
        run("tag", bid, "--remove", "instapaper-cli-test-2")
        assert run("delete", bid, "--yes") == {"deleted": [int(bid)]}
    assert run("list", "-n", "50", "-m", marker) == []
