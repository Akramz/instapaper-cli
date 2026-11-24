# instapaper-cli

`instapaper` reads and manages your [Instapaper](https://www.instapaper.com) bookmarks from the
terminal through Instapaper's [v2 API](https://www.instapaper.com/api/2/openapi.json). It prints
JSON, so coding agents (Claude Code, pi, Codex) can use it as easily as people.

instapaper-cli is an independent project. It is not made or supported by Instapaper.

## Install

Needs [uv](https://docs.astral.sh/uv/):

```console
uv tool install git+https://github.com/Akramz/instapaper-cli
instapaper login
```

Upgrade with `uv tool upgrade instapaper-cli`.

## Credentials

Register an application on Instapaper's Applications page (Settings > Applications) and
generate an access token for your own account. A free account works. `instapaper login` asks
for the token, checks it, and stores it in `~/.config/instapaper/auth.json` (mode 600).
`INSTAPAPER_TOKEN` overrides the file and `INSTAPAPER_CONFIG` moves it. `instapaper logout`
deletes it.

## Use

```console
instapaper list                          # newest 25 at home
instapaper list -f archive -n 100        # -f: home, archive, liked, a folder id, or all
instapaper list -t ml                    # one tag
instapaper list -f all -m "kv cache"     # scan the whole account by title, URL, author, description
instapaper text 123456                   # article as plain text (--html for the parsed HTML)
instapaper add https://example.com/post --title "Post" --tag ml
instapaper archive 123456 123457         # also: unarchive, like, unlike
instapaper move 123456 --folder 98765
instapaper update 123456 --progress 0.5  # or --title, --description
instapaper tag 123456 --add ml --remove todo
instapaper delete 123456 --yes           # permanent; prefer archive
```

Times are UTC. Exit codes: 1 = API error (JSON on stderr), 2 = bad usage, 4 = run
`instapaper login`.

The API has no search, for free or paid accounts. `list -m` pages through the list and matches
locally; `-f all -m` over about 1,000 bookmarks takes a few seconds. The v2 API has no folder
names or highlights, so folders are given by id (each bookmark lists its `folder_id`). PDFs and
videos have no parsed text.

## Test

```console
uv run --no-project --with-editable . --with pytest pytest
```

The test saves, changes and deletes one bookmark in the signed-in account (about 20 seconds).
It leaves two empty tags, `instapaper-cli-test` and `instapaper-cli-test-2`.
