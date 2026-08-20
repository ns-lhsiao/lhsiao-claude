# PR & GitHub Workflow

## PR & GitHub Workflow

- **Check PR state before pushing follow-up commits**. `gh pr view <num> --json state` — if MERGED, the commit becomes orphaned. Also when the user starts a squash-merge mid-edit, anything pushed between "merge clicked" and "squash completed" gets dropped. Confirm via `gh api repos/OWNER/REPO/compare/main...<branch>` — "behind by N, ahead by 0" = already merged. Failure: scheduled workflow still has the bug you "just fixed."
- **Transferred-repo origin URL lies**: a fork transferred to upstream still shows the old URL but pushes land upstream. Confirm with `gh pr view <num> --json headRepositoryOwner,headRepository`. Stop the redirect notice via `git remote set-url origin git@github.com:netSkope/<repo>.git`.
- **`gh pr edit` needs `read:project` scope**. Use REST instead: `gh api repos/OWNER/REPO/pulls/N -X PATCH -f body="..."`. The `-X PATCH` is required.
- **Moving a branch across remotes** can't retarget an open PR. Workflow: `gh pr close <num>` → `git push origin <branch>` → `gh pr create --head <branch>`. Delete the old-remote branch.
- **mf-client PR template**: H2 sections with emoji prefixes — `## 🎯 Jira Issue`, `## 📝 Description`, `## 🚧 Type of Change`, `## ✅ Checklist`, `## 🖼️ Screenshots`, `## 📌 Additional Notes`. Mirror `.github/pull_request_template.md` exactly.
- **webui PR template**: H4 sections (NOT H2) — `#### 🎯 Jira Issue`, `#### 📝 Change Description`, `#### 🚧 Type of Change`, `#### ✅ Checklist`, `#### 🧪 Manual Testing Done`, `#### 🖼️ Screenshots/Videos`, `#### 📌 Additional Notes`.
