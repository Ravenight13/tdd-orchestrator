---
description: "Evaluate decisions using chained mental models (First Principles, Pareto, Inversion, etc.)"
argument-hint: "[problem or decision to evaluate]"
allowed-tools:
  - Read
  - WebSearch
---

<objective>
Help users think through decisions and problems using proven mental models. Automatically selects 2-3 relevant models based on problem type, chains their outputs so insights build on each other, and synthesizes into an actionable recommendation.
</objective>

<triggers>
- "Help me evaluate..."
- "I need to decide..."
- "What should I do about..."
- "Help me think through..."
- "Should I..."
- Explicit: "Use the evaluate skill"
</triggers>

<quick_start>
**Implicit:** Just describe your problem. Claude detects evaluation-appropriate requests.
**Explicit:** "Help me evaluate whether to [decision]"
**Override:** "Use inversion and 5 whys for this" (specify models)
</quick_start>

<workflow>
1. **Parse** the problem or decision
2. **Select** 2-3 relevant mental models based on problem type
3. **Chain** models so each builds on prior insights
4. **Synthesize** into actionable recommendation
</workflow>

<success_criteria>
- Problem restated clearly and confirmed with user
- 2-3 models selected with rationale for selection
- Each model's output explicitly references prior model conclusions
- Final synthesis resolves tensions and provides a clear recommendation with confidence level
</success_criteria>

<the_12_mental_models>

### Analysis Models (What's really going on?)

| Model | Core Question | Best For |
|-------|---------------|----------|
| **First Principles** | What's fundamentally true here? | Challenging assumptions, finding root truths |
| **5 Whys** | Why does this happen? (x5) | Finding root causes of problems |
| **Occam's Razor** | What's the simplest explanation? | Cutting through complexity |

### Decision Models (What should I do?)

| Model | Core Question | Best For |
|-------|---------------|----------|
| **Via Negativa** | What should I remove/stop? | Avoiding additions, simplifying |
| **Opportunity Cost** | What am I giving up? | Comparing alternatives |
| **Inversion** | What would guarantee failure? | Risk identification, avoiding mistakes |

### Prioritization Models (What matters most?)

| Model | Core Question | Best For |
|-------|---------------|----------|
| **Pareto (80/20)** | What 20% drives 80% of results? | Focusing effort |
| **Eisenhower Matrix** | Urgent vs. important? | Task prioritization |
| **One Thing** | What single action enables everything else? | Finding leverage points |

### Consequence Models (What happens next?)

| Model | Core Question | Best For |
|-------|---------------|----------|
| **Second-Order Effects** | And then what? | Tracing consequences |
| **10/10/10** | How will I feel in 10 min/months/years? | Time-horizon perspective |
| **SWOT** | Strengths, weaknesses, opportunities, threats? | Strategic positioning |
</the_12_mental_models>

<auto_selection_heuristic>

Based on problem type, select models that chain well:

### "Should I add/build/create X?"
**Chain:** Via Negativa -> Opportunity Cost -> Second-Order
- First ask if we should do it at all
- Then what we give up by doing it
- Then trace the consequences

### "Why isn't this working?" / "What's wrong?"
**Chain:** 5 Whys -> First Principles -> Inversion
- Find root cause
- Challenge assumptions
- Identify failure modes to avoid

### "What should I focus on?" / "I'm overwhelmed"
**Chain:** Pareto -> One Thing -> Eisenhower
- Find the vital few
- Identify the leverage point
- Prioritize what remains

### "Is this the right approach?"
**Chain:** First Principles -> Occam's Razor -> Inversion
- Check fundamentals
- Simplify
- Verify against failure modes

### "What are the tradeoffs?"
**Chain:** SWOT -> Opportunity Cost -> 10/10/10
- Map the landscape
- Compare alternatives
- Add time perspective

### "Help me prioritize tasks/decisions"
**Chain:** Eisenhower -> Pareto -> One Thing
- Categorize by urgency/importance
- Find the vital few
- Pick the domino

### General / Unclear Problem Type
**Chain:** First Principles -> Inversion -> One Thing
- Understand fundamentals
- Avoid failure modes
- Find leverage
</auto_selection_heuristic>

<chaining_protocol>

Each model's output feeds the next:

```
Model 1 Output
     |
"Given that [Model 1 conclusion], now applying [Model 2]..."
     |
Model 2 Output (incorporates Model 1 insights)
     |
"Building on [Model 1 + 2 conclusions], applying [Model 3]..."
     |
Model 3 Output (synthesizes all)
     |
Final Synthesis
```

**Chaining Rules:**
- Reference prior model conclusions explicitly
- Build, don't repeat
- Contradictions between models = surface for user consideration
- Final synthesis resolves tensions into recommendation
</chaining_protocol>

<model_templates>

### First Principles
```
**Current Assumptions:**
- [Assumption]: [challenged: true/false/partially]

**Fundamental Truths:**
- [Truth]: [why irreducible]

**Rebuilt Understanding:**
Starting from fundamentals...

**New Possibilities:**
Without legacy assumptions...
```

### 5 Whys
```
**Problem:** [statement]
**Why 1:** [surface cause]
**Why 2:** [deeper]
**Why 3:** [deeper still]
**Why 4:** [approaching root]
**Why 5:** [root cause]

**Root Cause:** [the actual thing to fix]
**Intervention:** [action at root level]
```

### Occam's Razor
```
**Candidate Explanations:**
1. [Explanation]: Requires assumptions [A, B, C]
2. [Explanation]: Requires assumptions [D, E]

**Simplest Valid Explanation:**
[Fewest unsupported assumptions]
```

### Via Negativa
```
**Current State:** [what exists]

**Subtraction Candidates:**
- [Item]: Remove because [reason] -> Impact: [improvement]

**Keep (Passed the Test):**
- [Item]: Keep because [genuine value]

**After Subtraction:** [leaner state]
```

### Opportunity Cost
```
**Choice:** [what you're considering]

**Resources Required:**
- Time: [amount]
- Energy: [cognitive load]
- Other: [what else]

**Best Alternative Uses:**
- With that [resource], could instead: [alternative + value]

**True Cost:** Choosing this means NOT doing [best alternative]
**Verdict:** [worth it or not]
```

### Inversion
```
**Goal:** [what success looks like]

**Guaranteed Failure Modes:**
1. [Way to fail]: Avoid by [action]

**Anti-Goals (Never Do):**
- [Behavior to eliminate]

**Success By Avoidance:**
By not doing [X, Y, Z], success becomes likely because...
```

### Pareto (80/20)
```
**Vital Few (focus here):**
- [Factor]: [why it matters, specific action]

**Trivial Many (deprioritize):**
- [Brief list of what to defer]

**Bottom Line:** [where to focus]
```

### Eisenhower Matrix
```
**Q1: Do First** (Important + Urgent)
- [Item]: [action, deadline]

**Q2: Schedule** (Important + Not Urgent)
- [Item]: [when to do it]

**Q3: Delegate** (Not Important + Urgent)
- [Item]: [how to minimize]

**Q4: Eliminate** (Not Important + Not Urgent)
- [Item]: [permission to drop]
```

### One Thing
```
**Goal:** [desired outcome]

**The One Thing:**
[Action that enables/eliminates the most]

**Why This One:**
By doing this, [things] become easier/unnecessary because...

**Next Action:** [specific first step]
```

### Second-Order Effects
```
**Action:** [what's being considered]

**First-Order:** (Immediate)
- [Effect]

**Second-Order:** (And then what?)
- [Effect] -> leads to -> [Consequence]

**Third-Order:** (And then?)
- [Downstream consequences]

**Revised Assessment:**
After tracing the chain, this [is/isn't] worth it because...
```

### 10/10/10
```
**Decision:** [what you're choosing]

**Option A:**
- 10 minutes: [immediate feeling]
- 10 months: [medium-term reality]
- 10 years: [long-term impact]

**Option B:**
- 10 minutes: [immediate]
- 10 months: [medium-term]
- 10 years: [long-term]

**Recommendation:** [weighted toward longer horizons]
```

### SWOT
```
**Strengths (Internal +):** [advantage to leverage]
**Weaknesses (Internal -):** [disadvantage to mitigate]
**Opportunities (External +):** [favorable condition to capture]
**Threats (External -):** [risk to defend against]

**Strategic Move:** Use [strength] to capture [opportunity] while mitigating [weakness/threat]
```
</model_templates>

<output_format>

```
## Evaluation: [Problem/Decision Title]

**Problem:** [restated clearly]

**Models Selected:** [Model 1] -> [Model 2] -> [Model 3]
**Why These:** [brief rationale for selection]

---

### [Model 1 Name]
[Full model output]

**Key Insight:** [one-line takeaway for chaining]

---

### [Model 2 Name]
*Building on [Model 1] conclusion that [key insight]...*

[Full model output]

**Key Insight:** [one-line takeaway]

---

### [Model 3 Name]
*Given [Model 1 insight] and [Model 2 insight]...*

[Full model output]

**Key Insight:** [one-line takeaway]

---

## Synthesis

**Convergent Insights:**
[Where models agreed]

**Tensions:**
[Where models conflicted, with resolution]

**Recommendation:**
[Clear, actionable guidance]

**Confidence:** [High/Medium/Low] because [reason]
```
</output_format>

<examples>

### Example 1: Feature Decision
**User:** "Help me evaluate whether to add caching to our API"

**Auto-Select:** Via Negativa -> Opportunity Cost -> Second-Order

**Output:** Chains through models, concludes with actionable recommendation

### Example 2: Debugging
**User:** "Help me think through why our tests keep failing randomly"

**Auto-Select:** 5 Whys -> First Principles -> Inversion

**Output:** Finds root cause, challenges assumptions, identifies what to avoid

### Example 3: Prioritization
**User:** "I'm overwhelmed with tasks, help me figure out what to focus on"

**Auto-Select:** Pareto -> One Thing -> Eisenhower

**Output:** Identifies vital few, finds leverage point, creates action hierarchy
</examples>

<invocation>
**Implicit (recommended):**
Just describe your problem. Claude will detect evaluation-appropriate requests and invoke this skill.

**Explicit:**
- "Use the evaluate skill to help me with..."
- "Apply mental models to..."
- "Help me evaluate..."
</invocation>

<notes>
- Models can be run individually if user requests specific one
- User can override auto-selection: "Use inversion and 5 whys for this"
- If models produce conflicting recommendations, present the tension rather than hiding it
- Chaining should feel like a conversation building toward insight, not a checklist
</notes>
