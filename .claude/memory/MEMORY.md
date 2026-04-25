# Memory Index

Memory files for the Weaving Site project. These files capture decisions, context, and preferences that are not derivable from the code or requirements docs alone. A future agent or session should read these before starting work.

**All project memories live here** — in `.claude/memory/` inside the repo, version-controlled alongside the code.

## Files

- [project.md](project.md) — Platform vision, tech stack, key architectural decisions
- [project_issue_workflow.md](project_issue_workflow.md) — Plan to migrate STATUS.md task list to Gitea issues; label taxonomy, API patterns, migration checklist (not yet executed — needs GITEA_TOKEN_ISSUES in .env.local)
- [feedback.md](feedback.md) — How the user prefers to collaborate and work in this project:
  - Ask questions one at a time
  - Recommendations over options when asked
  - Document deferred features in phase2.md
  - Git workflow (main/dev/feature/*), merge gates, when to commit
  - Always pull dev before starting work (CI bot version-bumps the branch)
  - Append [skip ci] for documentation-only commits
  - Update STATUS.md and commit after each completed task
  - Regenerate environment lock files (environment.yml, requirements-lock.txt, .nvmrc) after any package install
  - All project memories must be saved here in the repo, not in ~/.claude/
