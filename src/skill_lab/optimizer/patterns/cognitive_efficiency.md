# Cognitive Efficiency Patterns

## Pattern: Verbose → Concise
*Source: "Add what the agent lacks, omit what it knows"*

### Before
```markdown
## Extract PDF text

PDF (Portable Document Format) files are a common file format that contains
text, images, and other content. To extract text from a PDF, you'll need to
use a library. pdfplumber is recommended because it handles most cases well.
```

### After
```markdown
## Extract PDF text

Use pdfplumber for text extraction. For scanned documents, fall back to
pdf2image with pytesseract.

import pdfplumber

with pdfplumber.open("file.pdf") as pdf:
    text = pdf.pages[0].extract_text()
```

### Principle
Cut explanations the agent already knows (what PDFs are, how HTTP works, what a database migration does). Jump straight to what's project-specific: tool choices, defaults, and exact usage patterns.

---

## Principle: Design coherent units
*Source: "Design coherent units"*

A skill should encapsulate a coherent unit of work, like a well-scoped function. Too narrow forces multiple skills to load for one task (overhead, conflicting instructions). Too broad becomes unfocused and hard to activate precisely. "Query a database and format results" is coherent; adding "database administration" probably isn't.

---

## Principle: Aim for moderate detail
*Source: "Aim for moderate detail"*

Overly comprehensive skills hurt — the agent struggles to extract what's relevant and may pursue unproductive paths. Concise stepwise guidance with a working example outperforms exhaustive documentation. If you're covering every edge case, most are better left to the agent's own judgment.
