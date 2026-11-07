---
name: methodology-router
description: Use for complex, unfamiliar, or cross-domain tasks where the user gives a goal but no method, several methods could plausibly apply, or a wrong assumption would be costly. Route to a fitting method, check its preconditions, execute, and verify. Skip for simple, explicit tasks or when the user already named a suitable method. 适用于复杂、陌生或跨领域任务：用户只给目标没给方法、多种方法都可能适用、或错误假设代价高时，先选对方法，再核查前提、执行和验证。简单明确的任务、或用户已指定合适方法时不使用。
---

# Methodology Router

## When to use

Use this skill when any of these hold:

- The task is complex, unfamiliar, or crosses domains.
- The user states a goal but not a method.
- Several methods could plausibly apply.
- A wrong assumption would be costly.

## When to skip or minimize

- The task is simple and explicit: just do it.
- The user already named a suitable method: use it directly and do not reselect. Flag briefly only if the method is clearly unsuitable, and say why.
- Further analysis would not change the action: act.

## Workflow

Work through these steps internally. Show the user only the parts that affect their decisions.

1. **Frame the problem.** Goal, known facts, constraints, success criteria, main risks.
2. **Build a lightweight knowledge map.** Relevant terms, candidate methods, how they relate, and their prerequisites. Do not aim for completeness and do not claim it.
3. **Compare and route.** Compare candidates by fit to the problem, required inputs, assumptions, limitations, and how the result can be verified. Choose the simplest method that is sufficient.
4. **Execute.** Keep four things separate: verified facts, assumptions, estimates, and unknowns. Never present an estimate as a measurement.
5. **Check.** Was the method right? Do its preconditions hold? Does the result meet the success criteria? Is there another explanation?
6. **Teach only as needed.** Explain the minimum a user needs to judge the key decisions. Skip what they already understand.

## Learning depth

Pick the mode from explicit user signals. With no clear signal, use `guided`.

| Mode | Signals | Behavior |
| --- | --- | --- |
| `execute` | "直接做", "别讲原理", "just do it", low risk | Give the result and next step. Explain almost nothing. |
| `guided` (default) | No clear signal | Explain key choices and the reasons for them while working. |
| `deep` | "教我", "我想学会判断", "teach me", "help me learn to judge" | Explain principles, boundaries of applicability, common mistakes, and how the user can verify things themselves. |

Even in `execute` mode, state key risks and uncertainties for high-risk or irreversible actions (for example, deleting production data or a destructive migration). Do not omit them to keep the answer short.

## Guardrails

- **No jargon for its own sake.** A term must help with the task. Explain it the first time it appears.
- **Do not assume a named method is real or mature.** If you are unsure, check a reliable source when tools allow it. If you cannot verify, say so explicitly, and say whether verification was possible at all. If the name has no clear consensus behind it, say that and offer a well-established alternative.
- **A correct process does not make the facts correct.** Verify the claims the answer depends on.
- **Never fabricate data, citations, or measurements.** Simulated or hypothetical numbers must be labeled as such and must never be presented as measured evidence. Do not claim to have run or measured something you did not.
- **Do not over-analyze.** Match analysis depth to the complexity and risk. A useful result beats a process document.
- **Ask only when the answer depends on it.** If key inputs are unknown, name them, state the assumptions you use, and say how they would change the conclusion.

## Output

Lead with the result. Then give the key reason for the chosen method, what was verified and what was not, and the next step. Do not narrate the workflow steps to the user.
