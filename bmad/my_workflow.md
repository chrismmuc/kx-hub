# My Story Implementation Workflow

## Overview
This workflow guides the complete implementation of user stories in the kx-hub project, from story creation through code review and deployment.

## ⚠️ Important: Command Execution Policy
**All slash commands listed in this workflow must be allowed to execute without interruption.**

The following commands are pre-approved for automatic execution:
- `/bmad:bmm:workflows:workflow-status` - Check current workflow status
- `/bmad:bmm:workflows:create-story` - Create story from epic
- `/bmad:bmm:workflows:story-context` - Generate context XML
- `/bmad:bmm:workflows:story-ready` - Mark story ready for development
- `/bmad:bmm:agents:dev` - Launch development agent
- `/bmad:bmm:workflows:code-review` - Run code review workflow
- `/bmad:bmm:workflows:story-done` - Mark story complete

**Test Execution:** Allow all `python3 -m pytest` commands when prompted.

## Phase 1: Story Setup

### 1.1 Get Story Details
- **Input:** User provides epic and story number (e.g., "Epic 4, Story 1" or "4.1")
- **Action:** Confirm the story scope and requirements

### 1.2 Create Story File
- **Command:** `/bmad:bmm:workflows:create-story`
- **What it does:** Generates story markdown file from epic specifications
- **Output:** `docs/stories/{epic}-{story}-{name}.md`

### 1.3 Generate Story Context
- **Command:** `/bmad:bmm:workflows:story-context`
- **What it does:** Creates comprehensive context XML file with:
  - Relevant code artifacts (functions, classes, modules)
  - Documentation references
  - Existing patterns and interfaces
  - Test examples and standards
- **Output:** `docs/stories/{epic}-{story}-{name}.context.xml`
- **Why important:** Provides AI agent with all necessary context to avoid hallucinations

## Phase 2: Story Development

### 2.1 Mark Story Ready
- **Command:** `/bmad:bmm:workflows:story-ready`
- **What it does:** Updates story status from `drafted` → `ready-for-dev`
- **Updates:** `docs/sprint-status.yaml`

### 2.2 Implement Story
- **Command:** `/bmad:bmm:agents:dev` then select `*develop-story`
- **What it does:**
  - Loads story and context automatically
  - Implements all tasks and subtasks
  - Writes comprehensive tests (unit, integration, e2e)
  - Runs all tests to validate implementation
  - Updates story file with completion notes
  - Marks story status as `review`
- **Test execution:** Allow `python3 -m pytest` commands when prompted
- **Continuous execution:** Agent runs until all tasks complete or hits a blocker

### 2.3 Verify Implementation
- **Manual checks:**
  - Review modified files in File List section
  - Verify all tasks marked `[x]`
  - Check test results (all passing)
  - Review completion notes for any concerns

## Phase 3: Code Review

### 3.1 Run Code Review
- **Command:** `/bmad:bmm:workflows:code-review`
- **What it does:**
  - Performs senior developer-level code review
  - Checks against story acceptance criteria
  - Identifies issues by severity (High/Med/Low)
  - Generates action items in story file
- **Output:** Review section added to story file

### 3.2 Address Review Findings (if any)
- **Command:** `/bmad:bmm:agents:dev` then `*develop-story` (resume mode)
- **What it does:**
  - Detects review continuation automatically
  - Prioritizes review action items
  - Marks both task checkbox AND review item when resolved
  - Tracks resolution in completion notes

## Phase 4: Finalize Story

### 4.1 Mark Story Done
- **Command:** `/bmad:bmm:workflows:story-done`
- **Prerequisites:**
  - All tasks complete
  - All tests passing
  - Code review approved (or findings resolved)
  - Definition of Done satisfied
- **What it does:** Updates status from `review` → `done`

### 4.2 Commit Changes
- **Action:** Create git commit with clear description
- **Commit message format:**
  ```
  feat(epic-{N}): Story {N}.{M} - {Story Title}

  {Brief description of changes}

  - {Key change 1}
  - {Key change 2}
  - {Key change 3}

  Tests: {X} unit tests added/modified, all passing
  Files: {list key files modified}

  🤖 Generated with Claude Code

  Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>
  ```
- **Example:**
  ```
  feat(epic-4): Story 4.1 - Create Unified search_kb Tool

  Consolidates 6 search tools into unified search_kb interface with flexible filters

  - Added search_kb function with intelligent routing (cluster/date/time/cards/semantic)
  - Registered tool in MCP server with complete JSON Schema
  - Implemented 11 comprehensive unit tests covering all ACs and edge cases

  Tests: 11 new unit tests added, 17/17 passing, no regressions
  Files: src/mcp_server/tools.py, src/mcp_server/main.py, tests/test_mcp_tools.py

  🤖 Generated with Claude Code

  Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>
  ```

### 4.3 Create Pull Request (if applicable)
- **Action:** Use `gh pr create` or create PR manually
- **PR Title:** `Story {N}.{M}: {Story Title}`
- **PR Description:** Include:
  - Link to story file
  - Summary of changes
  - Test results
  - Acceptance criteria checklist

## Quick Reference Commands

```bash
# Story workflow sequence
/bmad:bmm:workflows:create-story      # Create story from epic
/bmad:bmm:workflows:story-context     # Generate context XML
/bmad:bmm:workflows:story-ready       # Mark ready for dev
/bmad:bmm:agents:dev                  # Implement story
  → *develop-story                    # Select this option
/bmad:bmm:workflows:code-review       # Review implementation
/bmad:bmm:agents:dev                  # Address review findings (if needed)
  → *develop-story                    # Auto-detects review mode
/bmad:bmm:workflows:story-done        # Mark complete

# Check status anytime
/bmad:bmm:workflows:workflow-status   # Get current status and recommendations
```

## Best Practices

### Do's ✅
- Always generate story context before implementing
- Allow test execution when prompted (python3 -m pytest)
- Trust the dev agent to run continuously until completion
- Review the File List to understand what changed
- Run code review before marking done
- Write clear, descriptive commit messages

### Don'ts ❌
- Don't skip story-context generation (leads to hallucinations)
- Don't interrupt dev agent during implementation (let it run to completion)
- Don't mark story done without running code review
- Don't commit without verifying all tests pass
- Don't skip the manual verification step

## Troubleshooting

### Story status not updating
- Check `docs/sprint-status.yaml` for current status
- Ensure story key matches filename pattern
- Run `/bmad:bmm:workflows:workflow-status` for diagnostics

### Tests failing
- Check test output for specific failures
- Review implementation against acceptance criteria
- Use dev agent to fix issues: `/bmad:bmm:agents:dev` → `*develop-story`

### Missing context
- Re-run `/bmad:bmm:workflows:story-context` to regenerate
- Verify context file exists in story directory
- Check that relevant code artifacts are referenced

### Agent stops prematurely
- Check for HALT conditions in output
- Review error messages for blockers
- Resume with `/bmad:bmm:agents:dev` → `*develop-story`

## Example: Story 4.1 Walkthrough

**User:** "Implement Story 4.1"

**Steps executed:**
1. Story already created: `docs/stories/4-1-search-kb-unified.md` ✓
2. Context already generated: `docs/stories/4-1-search-kb-unified.context.xml` ✓
3. Story status: `ready-for-dev` ✓
4. Ran: `/bmad:bmm:agents:dev` → `3. *develop-story`
5. Agent implemented:
   - Task 1: search_kb function (350 lines, 5 routing modes)
   - Task 2: Tool registration in main.py
   - Task 3: 11 comprehensive unit tests
   - Task 4: Integration testing (manual step noted)
6. Tests: 17/17 passing
7. Files modified: 3 (tools.py, main.py, test_mcp_tools.py)
8. Status: `in-progress` → `review`
9. Ready for code review

**Result:** Complete implementation in one session, all ACs met, ready for review. 