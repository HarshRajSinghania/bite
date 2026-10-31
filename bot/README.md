# The bite-check app's welcome bot

`welcome.py` runs once an hour (`.github/workflows/bot.yml`). For each repo the bite-check app was newly installed
on, it opens one issue with an "Add Bite" link. The link opens GitHub's new-file page with `.github/workflows/bite.yml`
filled in for the repo's main language; the owner reads it and clicks **Commit changes**.

## Safety

- The app has one permission: **Issues: read and write**. Each run also asks GitHub for an issues-only token.
- The app's private key (`BITE_APP_KEY`) lives only in this repo's **bot** environment, which only `main` can use.
  Pull request checks and forks can't read it. It is not a repository secret.
- The workflow has no token permissions of its own, uses only `actions/checkout` pinned to an exact commit, and the
  script uses only Python's standard library and the `openssl` command.
- Installs on more than 10 repos at once get no issues, so nobody gets flooded. A repo never gets a second issue,
  even after the first is closed.
- Try it safely: Actions, **bot**, **Run workflow** with "Only print what it would post" ticked (the default).

## If the key leaks

1. App settings (github.com/settings/apps/bite-check), private keys: **Generate a private key**. A .pem file downloads.
2. Delete the old key there.
3. Repo Settings, Environments, **bot**, edit `BITE_APP_KEY`, paste the whole new .pem file.
4. Delete the downloaded .pem from your computer.

With issues-only permission, the worst a leaked key could do is post issues on repos where the app is installed.
