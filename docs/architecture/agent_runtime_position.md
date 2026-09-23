# Agent Runtime Position

## Purpose

This document captures the architectural position behind `sec-investigator`.

It is not a product pitch. It is a design statement about how the system should be understood, what problems it is trying to solve, and why the current rewrite direction is structurally different from the old KKS approach.

The goal is to build an enterprise-grade security agent system with open-source-grade architectural discipline.

## Position Summary

`sec-investigator` is not a generic multi-agent system. It is a unified, state-driven investigation runtime built on LangGraph.

LangGraph is used as the execution substrate, not as the business brain.

The old KKS problem was not weak tools, but fragmented runtime philosophy: `Guard`, `Plan`, and `ReAct` were parallel islands, routing was LLM-driven, and coordination leaked into the handler layer.

The rewrite corrects this by making the graph a state machine, keeping routing and policy in code, keeping tools in the security layer, and keeping surfaces thin.

Existing KKS tools and collectors are still valuable and production-proven; they do not need to be rediscovered, but they must be re-integrated under stricter state, layering, and runtime contracts.

The system should be understood as one runtime with many bounded specialists. The primary question is no longer "single-agent or multi-agent," but whether execution is unified, governed, observable, and constrained by explicit business boundaries.

Freedom is only valid inside a bounded graph.

## Core Position

`sec-investigator` should not be understood as a generic "AI agent application."

It should be understood as a bounded investigation runtime for security and operations scenarios, where:

- business boundaries define system boundaries
- system boundaries constrain agent behavior
- tools are domain assets, not prompt accessories
- state is the primary truth source
- routing is a software concern, not a free-form LLM concern

The system is not trying to maximize open-ended autonomy. It is trying to maximize reliable, auditable, domain-constrained execution.

## Why LangGraph Is the Right Substrate

LangGraph is the correct architectural substrate for this class of system because it is strongest where industrial agent systems actually need discipline:

- stateful execution
- checkpointing and recovery
- streaming
- routing
- human-in-the-loop interruption points
- orchestrator-worker execution patterns

That makes it fundamentally different from frameworks primarily optimized to strengthen general AI behavior in broad, everyday, unconstrained use cases.

In this context:

- LangGraph is a runtime substrate
- not the business brain
- not the policy system by itself
- not the domain model by itself

It is the execution scaffold that allows the domain system to be implemented without rebuilding foundational orchestration machinery from scratch.

## What Was Learned from Other Systems

Different systems were useful for different reasons.

From `cc-cli`, the key learning was engineering discipline around queries, tools, and practical model usage. The important lesson there is how to think from the source-code level about model invocation as part of a software system, not as an isolated prompt exercise.

From `Hermes`, the key learning was hierarchical governance, skill systems, and clear system-boundary definition. The value is not only capability composition, but understanding how capabilities are structured and constrained.

From LangGraph, the key value is different again: it provides a strong runtime scaffold, established patterns, and reusable packages that remove a large amount of low-value foundational engineering effort. That allows more focus on the actual architectural problem: how to map domain business boundaries into explicit system boundaries.

## What `sec-investigator` Is Actually Building

The rewrite should be understood through this formula:

**Autonomous security agent = LangGraph runtime substrate + KKS domain tools and business logic + strict state contracts + strict layered governance**

This formula needs careful interpretation.

The important word is not "autonomous." The important phrase is "bounded autonomy."

In a security system, freedom is only valid when it exists inside a bounded graph, where:

- node eligibility is controlled
- transitions are explicit
- state mutation is governed
- routing is policy-constrained
- execution is observable

The system should not be free in an unbounded space. It should only be free to choose among permitted actions inside a rigorously defined runtime.

## Old KKS: The Real Architectural Problem

The main problem in the original KKS was not that the tools were weak.

In fact, the tool and domain base was strong:

- the `agents/tools/` layer contained production-proven integrations
- ES DSL construction had real operational value
- Prometheus queries were grounded in actual usage
- CC and DDoS adapters had been validated in production
- domain resolution logic in `GFCollector` and `WAFCollector` came from real operational friction
- deduplication and alert-state handling were shaped by months of business use

That part of the system was not theoretical. It was real.

The real architectural problem was the runtime philosophy around those assets.

### 1. Three Parallel Runtime Islands

The old system had `Guard`, `Plan`, and `ReAct` as separate runtime islands.

These were not three strategies inside one runtime. They were three independent graphs with:

- separate state models
- separate node sets
- separate routing logic
- coordination pushed outside the graph

What coordinated them was not a unified runtime state machine, but external Redis-based bookkeeping in the handler layer.

That is a direct sign of graph-philosophy failure:

- the graph should have been the runtime center
- instead, the graph became only one local workflow tool among several systems

### 2. LLM-Driven Routing

In the old ReAct path, the supervisor used the LLM to decide the next node.

That made routing:

- less predictable
- less testable
- more expensive
- more sensitive to prompt drift

This is one of the most important architectural corrections in `sec-investigator`:

- the LLM should generate or refine `agent_task`
- routing itself should be code-driven and policy-driven

That is the difference between prompt orchestration and software orchestration.

### 3. The God Function Problem

`alert_handler.py` in the old system became a God function.

It simultaneously owned:

- entity extraction
- deduplication
- chart rendering
- multi-mode dispatch
- Feishu card construction
- table storage
- comparison report triggering

That file did not belong cleanly to graph, runtime, or surface. It existed because the architecture had no stable place for cross-cutting execution logic.

This is a classic sign of structural decay:

- if every layer can justify owning a piece of logic
- then no layer actually governs it

### 4. Inconsistent State Philosophy

The old system did not have one coherent state contract.

Examples included:

- reducer behavior that appended some fields and replaced others without one unified contract model
- flow-control semantics hidden in state fields such as `output_mode`
- mixed business and control fields such as `structured_response` and `supervisor_thought`
- different nodes implicitly assuming different meanings for the same shared state

This meant the graph was no longer a clean state machine. It was a shared mutable container.

### 5. Flow Hard-Coded into the Graph

The old `knowledge_expert` path being effectively mandatory at the start of a new session is a good example of the wrong design instinct.

That was not policy-driven routing. It was process hard-coded into the graph.

The correct architecture is:

- policies decide when knowledge augmentation is needed
- the graph executes state transitions
- the graph should not hard-code one inflexible procedural worldview

## What Changed in the New Understanding

The most important shift is this:

The old understanding of LangGraph was:

- the graph is a flowchart

The current understanding is:

- the graph is a state machine
- strategy belongs in code
- tools belong in the domain layer
- surfaces stay thin

Both approaches can produce software that "runs."

But they are radically different in:

- maintainability
- testability
- observability
- extension cost
- long-term evolution risk

This is why the rewrite is not just a refactor. It is a correction in runtime philosophy.

## Is `sec-investigator` Single-Agent or Multi-Agent?

Strictly speaking, the current system is best described as:

**one runtime with multiple bounded specialists**

It is not a classic "single agent" in the naive sense, because it clearly has specialist roles.

But it is also not a loosely coupled multi-agent society in which multiple semi-autonomous planners negotiate control of the system.

The more accurate description is:

**single-runtime, multi-specialist investigation system**

This distinction matters because, in enterprise security systems, the important question is no longer:

- is this single-agent or multi-agent?

The more important questions are:

- who owns routing authority?
- who owns state mutation authority?
- are specialists bounded workers or hidden planners?
- is execution policy unified?
- is the runtime observable and auditable?

If those questions are answered well, then the label "single-agent" versus "multi-agent" becomes secondary.

## Is That Question Still Important?

Yes, but it is no longer the first-order question.

For this system, the first-order question is:

**Is this a unified, governed, state-driven execution system?**

That is more important than whether the marketing label says single-agent or multi-agent.

For a security and operations system, the preferred architectural answer is:

- one runtime
- one truth-bearing state model
- one policy system
- many bounded specialists

That is healthier than pursuing a multi-agent identity for its own sake.

## Current LangGraph Usage: Correct but Still Basic

It is important to be precise about the current maturity level.

`sec-investigator` is using LangGraph correctly at the foundational level, but not yet deeply at the advanced orchestration level.

Today it is already aligned with:

- durable execution
- streaming
- HITL extension points
- routing
- basic orchestrator-worker execution

But it has not yet fully adopted more advanced production patterns such as:

- parallel fan-out and fan-in
- `Send`-driven dynamic worker dispatch
- subgraph-based responsibility packaging
- richer concurrent aggregation and divide-and-conquer orchestration

So the correct judgment is:

**the project uses LangGraph in a structurally correct foundational way, but it has not yet exhausted LangGraph's more advanced horizontal orchestration capabilities**

That is not a flaw by itself. It simply defines the current phase of maturity.

## Is Horizontal Scalability Healthy?

This depends on what kind of scaling is being discussed.

### 1. Business-Capability Scalability

At the architectural level, this is healthy.

The new structure makes it natural to add:

- a new adapter
- a new collector
- a new playbook
- a new specialist worker
- a new surface adapter
- a new schema or finding type

This is healthy horizontal growth because capabilities are added as bounded modules, not by cloning runtime patterns.

### 2. Runtime-Scale Scalability

This is only partially mature.

The architecture allows it, but the implementation has not yet fully proven it.

Reasons include:

- the graph is still mostly a serial supervisor-worker loop
- advanced parallel orchestration patterns are not yet in use
- some adapter and client lifecycle management remains incomplete
- surface-level hardening and tenancy concerns are still immature
- replay, integration, and benchmark coverage are still incomplete

So the correct conclusion is:

**the architecture is horizontally extensible in structure, but not yet fully demonstrated as horizontally scalable in runtime behavior**

## The Right Position on the Legacy Tooling Layer

It is correct to say that the existing tool and business base does not need to be rediscovered from zero.

However, that statement needs precision.

What can be reused with high confidence:

- business semantics
- operational query knowledge
- API integration experience
- field-level domain understanding
- production-shaped heuristics and workflow knowledge

What still must be revalidated in the new architecture:

- input and output contracts under the new runtime
- adapter lifecycle ownership
- event emission and observability behavior
- timeout and concurrency behavior
- consistency with the new state contract
- compliance with the new layering and policy model

So the correct statement is not:

- "the tool layer needs no more validation"

The correct statement is:

- "the business validity of the tool layer is already proven, but its runtime integration correctness must still be validated under the new architecture"

## Final Architectural Summary

The current rewrite should not be described as "moving KKS onto LangGraph."

That is too shallow.

The real change is this:

**the system is being transformed from a collection of parallel workflows into a unified, state-machine-driven, domain-bounded investigation runtime**

This is the real architectural value of `sec-investigator`.

And the right final principle is:

**freedom is only correct when it exists inside a bounded graph, where node choice is controlled, state is explicit, and policy governs execution**

That is the direction an enterprise-grade security agent system should follow.
