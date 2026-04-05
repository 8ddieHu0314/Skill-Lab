# Procedural Clarity Patterns

## Pattern: Menu → Default
*Source: "Provide defaults, not menus"*

### Before
```
You can use pypdf, pdfplumber, PyMuPDF, or pdf2image...
```

### After
```
Use pdfplumber for text extraction:

import pdfplumber

For scanned PDFs requiring OCR, use pdf2image with pytesseract instead.
```

### Principle
Pick a default. Mention alternatives briefly with their escape conditions. Don't present options as equal — that makes the agent pick arbitrarily.

---

## Pattern: Declaration → Procedure
*Source: "Favor procedures over declarations"*

### Before
```markdown
Join the `orders` table to `customers` on `customer_id`, filter where
`region = 'EMEA'`, and sum the `amount` column.
```

### After
```markdown
1. Read the schema from `references/schema.yaml` to find relevant tables
2. Join tables using the `_id` foreign key convention
3. Apply any filters from the user's request as WHERE clauses
4. Aggregate numeric columns as needed and format as a markdown table
```

### Principle
Teach the agent *how to approach* a class of problems, not *what to produce* for a specific instance. The first works only for this task; the second generalizes.

---

## Pattern: Prose → Template
*Source: "Templates for output format"*

### Before
```
Write a report with an executive summary, key findings with supporting data,
and recommendations.
```

### After
```markdown
# [Analysis Title]

## Executive summary
[One-paragraph overview of key findings]

## Key findings
- Finding 1 with supporting data
- Finding 2 with supporting data

## Recommendations
1. Specific actionable recommendation
2. Specific actionable recommendation
```

### Principle
When you need specific output format, provide a template. Agents pattern-match against concrete structures more reliably than prose descriptions.

---

## Pattern: Vague → Checklist
*Source: "Checklists for multi-step workflows"*

### Before
```
Process the form by analyzing it, mapping the fields, filling it out,
and verifying the output.
```

### After
```markdown
Progress:
- [ ] Step 1: Analyze the form (run `scripts/analyze_form.py`)
- [ ] Step 2: Create field mapping (edit `fields.json`)
- [ ] Step 3: Validate mapping (run `scripts/validate_fields.py`)
- [ ] Step 4: Fill the form (run `scripts/fill_form.py`)
- [ ] Step 5: Verify output (run `scripts/verify_output.py`)
```

### Principle
An explicit checklist helps the agent track progress and avoid skipping steps, especially with dependencies or validation gates.
