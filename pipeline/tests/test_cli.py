"""The `rce` command, as a reader runs it."""

import pymupdf

from rce_pipeline import cli


def test_rce_says_which_step_it_is_on(tmp_path, capsys):
    pdf = tmp_path / "book.pdf"
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "1.e4 e5 2.Nf3 Nc6")
    doc.save(pdf)

    cli.main([str(pdf)])

    captured = capsys.readouterr()
    # Not a terminal here, so one plain line per step and no spinner.
    assert "Reading the moves" in captured.err
    assert "\r" not in captured.err
    assert "Moves:" in captured.out
    assert (tmp_path / "book.rce").exists()



def pipeline_commits(installed_view: str | None, latest: str | None):
    """The last commit to touch pipeline/ as seen from a commit, and from main."""
    return lambda ref=None: installed_view if ref is not None else latest


def test_a_newer_pipeline_on_github_is_announced(monkeypatch):
    monkeypatch.delenv("RCE_NO_UPDATE_CHECK", raising=False)
    monkeypatch.setattr(cli, "_installed_commit", lambda: "head")
    monkeypatch.setattr(cli, "_pipeline_commit", pipeline_commits("aaa", "bbb"))
    assert "pipx reinstall rce-pipeline" in cli.update_notice()


def test_commits_outside_the_pipeline_are_no_update(monkeypatch):
    # Installed at a commit that only touched the app: the pipeline it carries
    # is still main's latest, so there is nothing to reinstall.
    monkeypatch.delenv("RCE_NO_UPDATE_CHECK", raising=False)
    monkeypatch.setattr(cli, "_installed_commit", lambda: "head")
    monkeypatch.setattr(cli, "_pipeline_commit", pipeline_commits("aaa", "aaa"))
    assert cli.update_notice() is None


def test_no_update_check_without_a_git_install_or_a_network(monkeypatch):
    monkeypatch.delenv("RCE_NO_UPDATE_CHECK", raising=False)
    # Run from a checkout: nothing installed from GitHub to compare.
    monkeypatch.setattr(cli, "_installed_commit", lambda: None)
    monkeypatch.setattr(cli, "_pipeline_commit", pipeline_commits("aaa", "bbb"))
    assert cli.update_notice() is None
    # GitHub out of reach: say nothing rather than fail.
    monkeypatch.setattr(cli, "_installed_commit", lambda: "head")
    monkeypatch.setattr(cli, "_pipeline_commit", pipeline_commits(None, None))
    assert cli.update_notice() is None
    # Turned off by the reader.
    monkeypatch.setenv("RCE_NO_UPDATE_CHECK", "1")
    monkeypatch.setattr(cli, "_pipeline_commit", pipeline_commits("aaa", "bbb"))
    assert cli.update_notice() is None


def test_a_newer_pipeline_is_offered_before_the_book_is_read(monkeypatch):
    # Laurent: the update is offered as a question when rce starts, and is
    # optional. Accepted, pipx reinstalls and the same command runs again on
    # the new version, which does not ask a second time.
    monkeypatch.setattr(cli, "update_notice", lambda: "A newer version of rce is available.")
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt="": "y")
    ran, relaunched = [], []
    monkeypatch.setattr(cli.subprocess, "run", lambda cmd, **kw: ran.append(cmd) or
                        cli.subprocess.CompletedProcess(cmd, 0))
    monkeypatch.setattr(cli.os, "execvpe", lambda f, args, env: relaunched.append((args, env)))

    cli.offer_update(["book.pdf"])

    assert ran == [["pipx", "reinstall", "rce-pipeline"]]
    (args, env), = relaunched
    assert args == ["rce", "book.pdf"] and env["RCE_NO_UPDATE_CHECK"] == "1"


def test_pressing_enter_accepts_the_update(monkeypatch):
    # Laurent: yes by default at a terminal; never asked when not at one.
    monkeypatch.setattr(cli, "update_notice", lambda: "A newer version of rce is available.")
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt="": "")
    ran = []
    monkeypatch.setattr(cli.subprocess, "run", lambda cmd, **kw: ran.append(cmd) or
                        cli.subprocess.CompletedProcess(cmd, 0))
    monkeypatch.setattr(cli.os, "execvpe", lambda f, args, env: None)

    cli.offer_update(["book.pdf"])

    assert ran == [["pipx", "reinstall", "rce-pipeline"]]
