## Description

Please include a concise summary of the changes in this pull request. If it closes an issue, mention it here.

Closes: #(issue)

## AI Disclosure

Using AI tools to write code is fine, but non-trivial use should be disclosed so that reviewers know where to look more carefully.

- [ ] I used AI to... [fill here]
- [ ] I did not use AI

## 🎯 PRs Should Target Issues

Before you create a PR, please check whether there is [an existing issue](https://github.com/charleemagn/mlogger/issues) for this change. If not, please create one first, unless the fix is trivial (a typo, a broken link). This keeps the discussion about *what* to do separate from the review of *how* it is done.

## Testing Your Code

1. PRs are merged only if the tests pass on CI. Please run them locally first: `python -m unittest discover test`
2. If you changed behavior, add or update a test in `test/`.
3. If you changed the interface, attach a screenshot.

## Checklist

- [ ] No new third-party dependencies
- [ ] The code still works on Python 3.9
- [ ] `CHANGELOG.md` is updated
