# workspace

Everything the tool writes lands here, so a scan never touches the system or the project
being examined.

```
projects/   repositories cloned by `scan --repo`, and any code copied in to test against
reports/    JSON reports
sessions/   saved `ask` conversations, one directory per project examined
```

The contents are gitignored; the directories themselves are kept.
