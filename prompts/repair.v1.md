# repair.v1

One correction round, and only one (SDD §9 stage 5). The validator has rejected
a plan and says exactly why; this prompt hands those reasons back and asks for a
complete replacement.

A replacement, not a patch: a patch has to be merged, and a merge is a second
place where the plan can become something nobody chose.

---

Your previous plan was rejected. Here is the plan you produced and what is wrong
with it.

## Your plan

{{PLAN}}

## What is wrong

{{ISSUES}}

Produce a **complete corrected plan**, not a change to the old one. Same schema,
same rules, same metrics and dimensions as before — you have not been given any
new ones, and a metric that was unavailable before is still unavailable.

If the issues show that no offered metric actually fits the question, return
`{"no_fit": true, "reason": "...", "data_exists": ...}` instead. Being told you
were wrong is a reason to reconsider whether anything fits, not only a reason to
try again.

Answer only with the structured object you have been given a schema for.
