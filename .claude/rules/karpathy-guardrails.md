# Behavioral Guardrails (Andrej Karpathy Rules)

These rules govern all AI coding interactions in this repository to prevent common LLM pitfalls (hallucinated complexity, drive-by refactoring, unverified assumptions).

## 1. Think Before Coding
- **Surface Tradeoffs**: Before touching code, explicitly state your understanding, plan, and any tradeoffs.
- **Clarify Ambiguity**: If a requirement has more than one plausible interpretation, ask the user before proceeding. Never silently pick an arbitrary approach.
- **Simpler Alternatives**: If a proposed request can be solved in a significantly simpler way, suggest the simpler way before coding.

## 2. Simplicity First
- **No Speculative Architecture**: Write code strictly for current, explicit requirements. Do not add hooks, configuration flags, base classes, or abstractions "for the future".
- **Compact Implementations**: If an implementation takes 150 lines but could cleanly be written in 40 lines, choose the 40-line implementation.
- **Minimal Dependencies**: Do not introduce third-party libraries when standard library features or existing dependencies suffice.

## 3. Surgical Changes
- **Targeted Diffs**: Keep diffs minimal and confined strictly to the files and functions needed to complete the task.
- **No Drive-by Refactoring**: Do not reformat unaffected functions, reorder unrelated imports, or rewrite working code.
- **Match Conventions**: Adhere strictly to existing naming conventions, typing practices, and formatting in the target file.
- **Clean Up Own Residue**: Remove unused variables or imports introduced by your own changes; leave existing code untouched.

## 4. Goal-Driven Execution
- **Verifiable Endpoints**: Frame every task with unambiguous success criteria (e.g., "new test passes", "concatenation check succeeds", "CLI returns code 0").
- **Verification Loop**: Run tests and commands to verify changes before concluding any turn.

