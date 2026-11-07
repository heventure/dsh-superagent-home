---
name: methodology-router
description: Use before execution when a task needs a method choice. Triggers include complex, unfamiliar, or cross-domain work; the user gives a goal but no method; several methods could plausibly apply; a named theory, framework, or metric is being used and its basis is unverified; the deliverable is an estimate, forecast, or schedule commitment whose inputs are unchecked; or a decision about whether a specific workload fits in memory, or how fast it will run, where the hardware or model inputs are not yet known. Skip when the task is simple and explicit, or when the user already scoped one deliverable — a definition, explanation, translation, summarization, rename, commit message, or a named statistical test on given data — do it, note any limitation, and do not route. If the user named a suitable method, use it and point out any broken precondition instead of reselecting. 适用于需要先选方法再执行的任务：复杂、陌生或跨领域的任务；用户只给目标没给方法；多种方法都可能适用；引用了未经核实的理论、框架或指标；或交付物是估算、预测、排期承诺而输入未经验证，或是判断某个负载能否放进显存、跑多快而硬件或模型输入未知。简单明确的任务，或用户已限定单一交付物（定义、解释、翻译、摘要、改名、提交信息、对给定数据做指定检验：直接做，说明局限即可）时不要使用；用户已指定合适方法时直接用，指出失效的前提，不重选。
---

# Methodology Router

## When to use

Use this skill when any of these hold:

- The task is complex, unfamiliar, or crosses domains.
- The user states a goal but not a method.
- Several methods could plausibly apply, and the choice would change what you do.
- A named theory, framework, or metric is being used and its basis is unverified.
- The deliverable is an estimate, forecast, or schedule commitment whose inputs are unchecked.
- The deliverable is a capacity, latency, or cost sizing judgement whose inputs are not yet known.
- A wrong assumption would be costly.

## When to skip or minimize

- The task is simple and explicit: just do it.
- The user named a suitable method: use it, and if one of its preconditions does not hold, say which and adjust the result — do not reselect a different method.
- The user scoped one deliverable or one calculation: do it, and state its limits in the answer.
- Further analysis would not change the action: act.

## Workflow

Work through these steps internally. Show the user only the parts that affect their decisions.

1. **Frame the problem.** Goal, known facts, constraints, success criteria, main risks.
2. **Build a lightweight knowledge map.** Relevant terms, candidate methods, how they relate, and their prerequisites. Do not aim for completeness and do not claim it.
3. **Compare and route.** For each candidate, state the question it answers, the inputs it requires, its assumptions, its limitations, and how its result can be checked. When several methods are chained, say in what order and why. Choose the simplest method that is sufficient.
4. **Execute.** Keep four things separate: verified facts, assumptions, estimates, and unknowns. Never present an estimate as a measurement.
5. **Check.** Was the method right? Do its preconditions hold? Does the result meet the success criteria? Is there another explanation?
6. **Teach only as needed.** Explain the minimum a user needs to judge the key decisions. Skip what they already understand.

## Diagnosing a performance problem

Do not start from a list of optimizations. Use this order, and say which step the current evidence supports:

1. **Tracing first — where does the time go?** Break the end-to-end path into spans (model calls, retrieval, each tool, memory, queueing) and compare p50 and p95. This answers "which part is slow"; it cannot explain why a specific function is slow. Move on only when a span dominates or the tail has a visible shape.
2. **Profiling second — why is that part slow?** Profile the code or runtime of the span that tracing already identified: CPU, allocation, lock waits, serialization. Profiling answers "why", given a known hotspot. Profiling without a located hotspot mostly produces noise.
3. **Ablation last — does this component earn its place?** Removing or disabling a component answers "what does it contribute", not "what is slow". It needs fixed inputs, repeated runs, and a quality metric, because a component can speed things up while making results worse.

Even when tracing is clearly the first step, say what profiling and ablation would each answer and what evidence would make them worth doing — the user is choosing a diagnostic path, not just ordering instrumentation. State the evidence that would justify the next step. Never assert a bottleneck, attribute time, or promise a speed-up without measurement.

## Capacity and hardware claims

- **Name the unknowns first.** Hardware, model, backend, quantization, context length, concurrency, and workload shape decide the answer; if any is missing, say so and make the answer conditional.
- **Budget in three parts.** Weights, KV cache (which grows with context length times parallel slots), and runtime/workspace overhead. Compare their sum with the measured peak, not with the nominal card size.
- **Measure, do not infer.** A repeatable benchmark needs a fixed prompt set, several repetitions, and at least TTFT, prefill, decode, peak memory, and a quality regression check. Change one variable per run.
- **No unmeasured numbers.** Do not give speed figures, "best" configurations, or hardware verdicts for a machine you have not measured. Throughput quoted from vendor pages or community benchmarks is someone else's measurement: it is not evidence for this machine, so do not build a recommendation on it — name the benchmark the user has to run instead.
- **No off-the-shelf verdict.** "This model plus these flags" is a hardware verdict unless it is conditional on measured results from that machine.

## Estimates and predictions

- An estimate is only as good as its inputs. Before computing, state what the inputs would have to be: historical estimates against actuals, a reference class, the dependency and parallelism structure, and ranges with a stated basis.
- If those inputs are missing or too thin, lead with that: the result cannot support a credible probability claim or a schedule commitment. The next step is collecting inputs, not picking a number.
- A demonstration computation may follow, but it must be labelled a scenario under stated assumptions, and the conclusion and next step must still foreground the data gap. Never phrase a scenario result as "commit to X".
- When the user asks for a date they can schedule or commit against, say plainly that no such date is supportable from these inputs, and give the collection plan first. If you show scenario dates, label them "assumption-only illustration — not for scheduling or commitment", do not recommend one date over another, and do not call any of them the date to promise.
- Show how the result moves when the assumptions change, and never use iteration counts or decimal places to imply accuracy.

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
- **A framework is not a measurement.** A number you did not measure is not a measurement, and a method you did not compare is not a selection.
- **Never fabricate data, citations, or measurements.** Simulated or hypothetical numbers must be labeled as such and must never be presented as measured evidence. Do not claim to have run or measured something you did not.
- **Do not over-analyze.** Match analysis depth to the complexity and risk. A useful result beats a process document.
- **Ask only when the answer depends on it.** If key inputs are unknown, name them, state the assumptions you use, and say how they would change the conclusion.

## Output

Lead with the result. Then give the key reason for the chosen method, what was verified and what was not, and the next step. Do not narrate the workflow steps to the user.
