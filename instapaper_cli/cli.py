import json
import re
import sys
import time
from datetime import UTC, datetime
from html.parser import HTMLParser

import click

from . import client

KINDS = {1: "email", 2: "video", 3: "pdf", 4: "social", 5: "text", 6: "markdown", 7: "chat"}
BLOCK = {
    "p",
    "ul",
    "ol",
    "div",
    "br",
    "li",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "blockquote",
    "pre",
    "tr",
    "section",
    "article",
    "figure",
    "figcaption",
    "hr",
}


class TextParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.out = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "head"):
            self.skip += 1
        elif tag in BLOCK:
            self.out.append("\n- " if tag == "li" else "\n\n")
            if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
                self.out.append("#" * int(tag[1]) + " ")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "head"):
            self.skip = max(0, self.skip - 1)
        elif tag in BLOCK and tag != "li":
            self.out.append("\n\n")

    def handle_data(self, data):
        if not self.skip:
            self.out.append(re.sub(r"\s+", " ", data))


def html_to_text(html: str) -> str:
    p = TextParser()
    p.feed(html)
    lines = [" ".join(line.split()) for line in "".join(p.out).split("\n")]
    text, blank = [], True
    for line in lines:
        if line or not blank:
            text.append(line)
        blank = not line
    return "\n".join(text).strip() + "\n"


def iso(ts):
    return datetime.fromtimestamp(int(ts), UTC).strftime("%Y-%m-%dT%H:%M:%SZ") if ts else None


def short(text, n=200):
    return text if not text or len(text) <= n else text[: n - 1].rstrip() + "…"


def bookmark(b: dict) -> dict:
    out = {
        "id": b["id"],
        "title": b.get("title"),
        "url": b.get("url"),
        "author": b.get("author"),
        "description": short(b.get("description")),
        "kind": KINDS.get(b.get("category")),
        "saved": iso(b.get("time")),
        "progress": round((b.get("progress") or {}).get("percentage") or 0, 3),
        "liked": b.get("liked"),
        "archived": b.get("archived"),
        "folder_id": b.get("folder_id"),
        "tags": [t["name"] for t in b.get("tags") or []],
        "private_source": b.get("private_source"),
    }
    return {k: v for k, v in out.items() if v not in (None, "", [])}


def emit(data):
    click.echo(json.dumps(data, indent=2, ensure_ascii=False))


def matches(b: dict, text: str) -> bool:
    return any(text.lower() in (b.get(k) or "").lower() for k in ("title", "url", "description", "author"))


def section(folder: str, tag: str | None) -> dict:
    if tag:
        return {"tag": tag}
    if folder == "all":
        return {"since": 1}
    if folder.isdigit():
        return {"folder_id": int(folder)}
    if folder in ("home", "archive", "liked"):
        return {"section": folder}
    raise click.BadParameter("use home, archive, liked, all or a folder id", param_hint="--folder")


def section_body(folder: str) -> dict:
    if folder not in ("home", "archive") and not folder.isdigit():
        raise click.BadParameter("use home, archive or a folder id", param_hint="--folder")
    return {"section": folder}


def each(method: str, ids, suffix: str, body=None):
    emit([bookmark(client.request(method, f"/bookmarks/{i}{suffix}", body=body)) for i in ids])


class Cli(click.Group):
    def invoke(self, ctx):
        try:
            return super().invoke(ctx)
        except client.NeedsLogin as e:
            click.echo(f"Not signed in ({e}). Run: instapaper login", err=True)
            sys.exit(4)
        except client.ApiError as e:
            click.echo(json.dumps({"error": {"code": e.code, "message": e.message}}), err=True)
            sys.exit(1)


@click.group(cls=Cli)
def cli():
    """Read and manage your Instapaper bookmarks. Prints JSON."""


@cli.command()
@click.option("--token", help="Access token from instapaper.com > Settings > Applications. Prompted for when omitted.")
def login(token):
    """Save an access token for your account."""
    token = token or click.prompt("Access token (instapaper.com > Settings > Applications)", hide_input=True, err=True)
    total = client.request("GET", "/bookmarks", {"limit": 1}, bearer=token)["total"]
    client.save({"token": token})
    click.echo(f"Signed in ({total} bookmarks at home). Token saved to {client.STATE}", err=True)


@cli.command()
def logout():
    """Forget the saved token."""
    client.STATE.unlink(missing_ok=True)
    click.echo("Logged out.", err=True)


@cli.command("list")
@click.option("--folder", "-f", default="home", show_default=True, help="home, archive, liked, a folder id, or all.")
@click.option("--tag", "-t", help="List one tag instead of a folder.")
@click.option("--limit", "-n", default=25, show_default=True, type=click.IntRange(1), help="Most bookmarks to print.")
@click.option("--offset", default=0, type=click.IntRange(0), help="Skip this many first.")
@click.option("--match", "-m", help="Scan the whole list for this text in title, URL, author or description.")
def list_(folder, tag, limit, offset, match):
    """List bookmarks, newest first."""
    params, out = section(folder, tag), []
    while len(out) < limit:
        size = 500 if match else min(limit - len(out), 500)
        data = client.request("GET", "/bookmarks", {**params, "limit": size, "offset": offset})
        page = data["bookmarks"]
        got = len(page) + len(data.get("deleted_ids", []))
        offset += got
        out += [bookmark(b) for b in page if not match or matches(b, match)]
        if got < size:
            break
    emit(out[:limit])


@cli.command()
@click.argument("bookmark_id", type=int)
@click.option("--html", is_flag=True, help="Print the parsed HTML body instead of plain text.")
def text(bookmark_id, html):
    """Print an article's text."""
    r = client.request("GET", f"/bookmarks/{bookmark_id}/parse")
    meta, content = r["metadata"], r["content"]
    body = content.get("body")
    if not body:
        raise client.ApiError(404, "Instapaper has no parsed text for this bookmark (PDFs and videos have none); open its URL")
    if html:
        click.echo(body)
        return
    info = [(meta.get("author") or {}).get("name"), f"{content['words']} words" if content.get("words") else None]
    if content.get("paywalled"):
        info.append("paywalled: may be only a preview")
    head = f"# {meta.get('title') or ''}\n\n" + (" · ".join(i for i in info if i) + "\n\n" if any(info) else "")
    click.echo(head + html_to_text(body), nl=False)


@cli.command()
@click.argument("url")
@click.option("--title", help="Saves faster when given.")
@click.option("--description")
@click.option("--folder", "-f", type=int, help="Folder id.")
@click.option("--tag", "-t", "tags", multiple=True)
@click.option("--archive", is_flag=True, help="Save straight to the archive.")
def add(url, title, description, folder, tags, archive):
    """Save a URL. Saving one you already have updates it and moves it to the top."""
    body = {"url": url, "title": title, "description": description, "folder_id": folder, "archived": archive}
    body = {k: v for k, v in body.items() if v not in (None, False)} | ({"tags": [{"name": t} for t in tags]} if tags else {})
    emit(bookmark(client.request("POST", "/bookmarks", body=body)))


@cli.command()
@click.argument("bookmark_id", type=int)
@click.option("--title")
@click.option("--description")
@click.option("--progress", type=click.FloatRange(0, 1), help="Reading progress, 0.0 to 1.0.")
def update(bookmark_id, title, description, progress):
    """Change a bookmark's title, description or reading progress."""
    body = {k: v for k, v in {"title": title, "description": description}.items() if v is not None}
    if progress is not None:
        body["progress"] = {"percentage": progress, "timestamp": int(time.time())}
    if not body:
        raise click.UsageError("pass --title, --description or --progress")
    each("POST", [bookmark_id], "", body)


@cli.command()
@click.argument("ids", nargs=-1, required=True, type=int)
def archive(ids):
    """Move bookmarks to the archive."""
    each("POST", ids, "/move", {"section": "archive"})


@cli.command()
@click.argument("ids", nargs=-1, required=True, type=int)
def unarchive(ids):
    """Move bookmarks back home."""
    each("POST", ids, "/move", {"section": "home"})


@cli.command()
@click.argument("ids", nargs=-1, required=True, type=int)
@click.option("--folder", "-f", required=True, help="home, archive or a folder id.")
def move(ids, folder):
    """Move bookmarks to a folder."""
    each("POST", ids, "/move", section_body(folder))


@cli.command()
@click.argument("ids", nargs=-1, required=True, type=int)
def like(ids):
    """Like bookmarks."""
    each("POST", ids, "/like")


@cli.command()
@click.argument("ids", nargs=-1, required=True, type=int)
def unlike(ids):
    """Unlike bookmarks."""
    each("DELETE", ids, "/like")


def tag_id(name: str) -> int:
    for b in client.request("GET", "/bookmarks", {"tag": name, "limit": 1})["bookmarks"]:
        for t in b.get("tags", []):
            if t["name"].lower() == name.lower():
                return t["id"]
    raise click.BadParameter(f"no tag named {name!r}", param_hint="--remove")


@cli.command()
@click.argument("ids", nargs=-1, required=True, type=int)
@click.option("--add", "-a", "adds", multiple=True, help="Tag to add; created if new.")
@click.option("--remove", "-r", "removes", multiple=True, help="Tag to remove.")
def tag(ids, adds, removes):
    """Add or remove tags on bookmarks."""
    if not adds and not removes:
        raise click.UsageError("pass --add or --remove")
    body = {"add_tags": [{"name": t} for t in adds], "remove_tags": [{"id": tag_id(t)} for t in removes]}
    emit({i: [t["name"] for t in client.request("POST", f"/bookmarks/{i}/tags", body=body)["tags"]] for i in ids})


@cli.command()
@click.argument("ids", nargs=-1, required=True, type=int)
@click.option("--yes", is_flag=True, help="Required: deletion is permanent. Use archive to keep them.")
def delete(ids, yes):
    """Permanently delete bookmarks."""
    if not yes:
        raise click.UsageError("delete is permanent; pass --yes, or use `instapaper archive`")
    for i in ids:
        client.request("DELETE", f"/bookmarks/{i}")
    emit({"deleted": list(ids)})
