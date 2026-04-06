# Error Resilience Patterns

## Pattern: Scattered warnings → Gotchas section
*Source: "Gotchas sections"*

### Before
```markdown
## Querying users
Remember to filter out deleted accounts.

## Finding a user
Note: the ID field name varies between services.

## Health checks
Warning: the health endpoint doesn't verify database connectivity.
```

### After
```markdown
## Gotchas

- The `users` table uses soft deletes. Queries must include
  `WHERE deleted_at IS NULL` or results will include deactivated accounts.
- The user ID is `user_id` in the database, `uid` in the auth service,
  and `accountId` in the billing API. All three refer to the same value.
- The `/health` endpoint returns 200 as long as the web server is running,
  even if the database connection is down. Use `/ready` for full health.
```

### Principle
Gotchas are concrete corrections to mistakes the agent would otherwise make. Consolidate scattered warnings into a dedicated Gotchas section in SKILL.md (not a separate reference file) so the agent sees them before encountering the situation. Keep them specific, not generic advice.

---

## Pattern: Linear → Validation loop
*Source: "Validation loops"*

### Before
```markdown
Make your edits, then commit.
```

### After
```markdown
1. Make your edits
2. Run validation: `python scripts/validate.py output/`
3. If validation fails:
   - Review the error message
   - Fix the issues
   - Run validation again
4. Only proceed when validation passes
```

### Principle
Instruct the agent to validate its own work before moving on. Pattern: do work, run validator, fix issues, repeat until passing.

---

## Pattern: Direct execution → Plan-validate-execute
*Source: "Plan-validate-execute"*

### Before
```markdown
Fill out the PDF form with the user's data and save the result.
```

### After
```markdown
1. Extract form fields: `python scripts/analyze_form.py input.pdf` → `form_fields.json`
2. Create `field_values.json` mapping each field name to its intended value
3. Validate: `python scripts/validate_fields.py form_fields.json field_values.json`
   (checks every field name exists, types are compatible, required fields aren't missing)
4. If validation fails, revise `field_values.json` and re-validate
5. Fill the form: `python scripts/fill_form.py input.pdf field_values.json output.pdf`
```

### Principle
For batch or destructive operations, have the agent create an intermediate plan in a structured format, validate against a source of truth, then execute. The validation step gives the agent enough information to self-correct before damage is done.
