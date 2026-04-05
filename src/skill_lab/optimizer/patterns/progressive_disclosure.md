# Progressive Disclosure Patterns

## Pattern: Generic reference → Conditional load
*Source: "Structure large skills with progressive disclosure"*

### Before
```markdown
See `references/` for details.
```

### After
```markdown
Read `references/api-errors.md` if the API returns a non-200 status code.
```

### Principle
When a skill legitimately needs content beyond the 500-line / 5,000-token budget, move detail to `references/` or similar, and tell the agent *when* to load each file. On-demand loading keeps SKILL.md lean while preserving access to depth when needed. A vague pointer ("see references/") is not progressive disclosure — the agent doesn't know when to look.
