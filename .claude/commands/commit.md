Create a git commit following the Conventional Commits specification exactly.

## Specification

Format:
```
<type>[optional scope]: <description>

[optional body]

[optional footer(s)]
```

### Types (always lowercase)
- `feat` — new feature (SemVer MINOR)
- `fix` — bug fix (SemVer PATCH)
- `refactor` — code change that is neither a fix nor a feature
- `docs` — documentation only
- `style` — formatting/whitespace, no logic change
- `perf` — performance improvement
- `test` — adding or fixing tests
- `build` — build system or dependency changes
- `ci` — CI configuration changes
- `chore` — other maintenance

### Rules
- Type is **always lowercase**
- One space after the colon, description immediately follows (no capital letter required)
- Scope is optional, written in parentheses: `feat(parser): add ability to parse arrays`
- Body is optional, separated from subject by one blank line
- Footers are optional, separated from body by one blank line, using git trailer format: `Token: value` or `Token #value`
- Breaking changes: append `!` after type/scope (`feat!: drop support for Python 3.9`) and/or add footer `BREAKING CHANGE: <description>`
- **Never add `Co-Authored-By` trailer**

### Examples
```
feat(grid): add zoom controls to viewport

fix: prevent crash when loading empty project

refactor(grid-size): replace spinboxes with slider+spinbox rows

feat!: remove deprecated export format

fix(auth): handle null token on login

BREAKING CHANGE: `config.json` schema updated, old format no longer supported
```

## Steps

1. Run `git status` and `git diff` (staged + unstaged) to review all changes.
2. Run `git log --oneline -5` to match the repo's existing commit style.
3. Stage relevant files with specific file names (avoid `git add -A`).
4. Draft a subject line: pick the correct lowercase type, optional scope, concise description.
5. Add a body if the change needs context beyond the subject.
6. Commit using a heredoc to preserve formatting:

```bash
git commit -m "$(cat <<'EOF'
type(scope): description

Optional body here.
EOF
)"
```

7. Run `git status` to confirm the commit succeeded.
