# Generate Trigger Tests

Generate comprehensive trigger tests for agent skills to validate proper activation behavior. Creates test cases for all 4 trigger types.

## Output Format

Output ONLY valid YAML with no markdown fences, no explanations, no commentary.

The YAML must follow this exact structure:

```yaml
skill: <skill-name>

test_cases:
  # === EXPLICIT TESTS ===
  # Direct invocation with $ prefix - should always trigger
  - id: explicit-1
    name: "Descriptive name for this test"
    type: explicit
    prompt: "$<skill-name> <action>"
    expected: trigger

  # === IMPLICIT TESTS ===
  # Describes the need without naming the skill
  - id: implicit-1
    name: "Descriptive name for this test"
    type: implicit
    prompt: "<scenario description>"
    expected: trigger

  # === CONTEXTUAL TESTS ===
  # Realistic prompts with domain context
  - id: contextual-1
    name: "Descriptive name for this test"
    type: contextual
    prompt: "<realistic noisy prompt>"
    expected: trigger

  # === NEGATIVE TESTS ===
  # Should NOT trigger - adjacent but distinct requests
  - id: negative-1
    name: "Descriptive name for this test"
    type: negative
    prompt: "<related but different request>"
    expected: no_trigger
```

### Test Case Fields

| Field | Required | Description |
|-------|----------|-------------|
| `id` | Yes | Unique identifier following pattern `<type>-<number>` (e.g., explicit-1, negative-2) |
| `name` | Yes | Short human-readable label describing WHAT the test validates |
| `type` | Yes | One of: `explicit`, `implicit`, `contextual`, `negative` |
| `prompt` | Yes | The test prompt to send |
| `expected` | Yes | Either `trigger` or `no_trigger` |

## Trigger Type Definitions

### Explicit Tests (generate 3)

Direct skill invocation using the `$<skill-name>` prefix.

- Every prompt MUST start with `$<skill-name>`
- Vary the commands/actions to cover different skill capabilities
- If the skill content mentions slash commands (e.g., `/review`, `/pr`) or alternative invocation methods, include at least one explicit test for each
- expected: `trigger`

Example for a "create-report" skill:
```yaml
- id: explicit-1
  name: "Generate sales summary report"
  prompt: "$create-report generate a sales summary"
- id: explicit-2
  name: "Generate Q4 metrics report"
  prompt: "$create-report for Q4 metrics"
```

### Implicit Tests (generate 3)

Describe the user's NEED without naming the skill. Tests whether the skill's name and description alone enable autonomous selection by an agent.

- MUST NOT use the `$<skill-name>` prefix
- MUST NOT mention the skill name
- MUST NOT mention the specific technology, library, or framework by name (e.g., for an "ant-design-skill", do NOT say "Ant Design" or "antd" — describe the UI pattern instead)
- Describe what the user wants to accomplish in natural language
- Focus on the USER'S PROBLEM or goal, not the tool that solves it

GOOD implicit examples:
```yaml
- id: implicit-1
  name: "Generate quarterly sales summary"
  prompt: "I need to generate a summary document of our quarterly sales data"
- id: implicit-2
  name: "Create project metrics document"
  prompt: "Can you create a summary document of the project metrics?"
```

BAD implicit examples (DO NOT generate triggers like these):
- `"Create a report using the reporting framework"` — names the technology
- `"I need report generation with charts, tables, and PDF export"` — paraphrases the SKILL.md bullet points instead of describing a real user need

### Contextual Tests (generate 3)

The user is in the middle of a real task and the skill need emerges from the SITUATION. The prompt includes project details, constraints, and surrounding context with the core request embedded in a longer narrative.

- Must include realistic project context, constraints, or workflow details
- The skill need should be INFERRED from the situation, not explicitly stated
- DO NOT just add extra words around an explicit or implicit trigger
- DO NOT embed literal tool commands, CLI syntax, or API calls in the prompt
- Think: "What would a real user say mid-project when they need this skill?"
- expected: `trigger`

GOOD contextual example:
```yaml
- id: contextual-1
  name: "Board meeting Q4 performance report"
  prompt: "I'm preparing for the board meeting next week. We need a comprehensive document showing our Q4 performance. Can you pull together the sales data and create something presentable?"
```

BAD contextual examples (DO NOT generate triggers like these):
- `"I'm working on the project. $create-report for Q4 sales data. Thanks."` — just an explicit trigger with noise around it
- `"Run create-report --format=pdf --data=sales.csv for the Q4 summary"` — embeds literal CLI commands

### Negative Tests (generate 4)

Requests that are adjacent to the skill's domain but should NOT activate it. Essential for catching false positives and over-eager triggering.

- At least 2 MUST be near-miss boundary tests from the SAME domain (adjacent but distinct actions)
- Avoid obvious non-matches from completely unrelated domains
- Test similar actions on different objects, or different actions on similar objects
- expected: `no_trigger`

GOOD negative examples for a "create-report" skill:
```yaml
- id: negative-1
  name: "Reading PDF (not creating)"
  prompt: "How do I read a PDF report?"
- id: negative-2
  name: "Deleting reports (not creating)"
  prompt: "Delete the old quarterly reports"
- id: negative-3
  name: "Asking about tools (informational)"
  prompt: "What's the best reporting tool?"
```

BAD negative example (DO NOT generate triggers like these):
- `"Set up a Kubernetes cluster"` — completely unrelated domain, not a useful boundary test

## Complete Example

For a skill named `write-commit-message`:

```yaml
skill: write-commit-message

test_cases:
  # === EXPLICIT TESTS ===
  - id: explicit-1
    name: "Direct invocation for recent changes"
    type: explicit
    prompt: "$write-commit-message for the changes I just made"
    expected: trigger

  - id: explicit-2
    name: "Direct invocation with format preference"
    type: explicit
    prompt: "$write-commit-message with conventional format"
    expected: trigger

  - id: explicit-3
    name: "Direct invocation for staged files"
    type: explicit
    prompt: "$write-commit-message for the staged files"
    expected: trigger

  # === IMPLICIT TESTS ===
  - id: implicit-1
    name: "Write commit message for staged changes"
    type: implicit
    prompt: "I need to write a commit message for my staged changes"
    expected: trigger

  - id: implicit-2
    name: "Draft commit message with best practices"
    type: implicit
    prompt: "Help me draft a good commit message following best practices"
    expected: trigger

  - id: implicit-3
    name: "Describe changes for version control"
    type: implicit
    prompt: "I want to describe my code changes before saving them to version control"
    expected: trigger

  # === CONTEXTUAL TESTS ===
  - id: contextual-1
    name: "Auth module refactor with JWT details"
    type: contextual
    prompt: "I just finished refactoring the authentication module. The changes include updating the JWT validation and adding refresh token support. Can you help me write a proper commit message for this?"
    expected: trigger

  - id: contextual-2
    name: "PR with login bug fix"
    type: contextual
    prompt: "Working on a PR for the new feature. Need to commit these files but not sure how to phrase the message. It's a bug fix for the login flow."
    expected: trigger

  - id: contextual-3
    name: "Multi-file refactor needing description"
    type: contextual
    prompt: "I've been cleaning up the codebase all morning — renamed some variables, extracted a helper function, and fixed a typo in the README. How should I describe all of this?"
    expected: trigger

  # === NEGATIVE TESTS ===
  - id: negative-1
    name: "Ask how to run git commit"
    type: negative
    prompt: "How do I run git commit?"
    expected: no_trigger

  - id: negative-2
    name: "View git log history"
    type: negative
    prompt: "Show me the git log for this repository"
    expected: no_trigger

  - id: negative-3
    name: "Undo last commit"
    type: negative
    prompt: "Undo my last commit"
    expected: no_trigger

  - id: negative-4
    name: "Ask about conventional commit types"
    type: negative
    prompt: "What are the conventional commit types?"
    expected: no_trigger
```

## Quality Checklist

Before outputting, verify:
1. Implicit prompts do NOT mention the skill name, $ prefix, OR technology/library/framework name
2. Contextual prompts describe a SITUATION, not just a request with extra words around it
3. At least 2 negatives are near-miss boundary tests from the same domain
4. All prompts sound like something a real user would actually say
5. The 4 categories are clearly differentiated — no two tests from different categories should be interchangeable
