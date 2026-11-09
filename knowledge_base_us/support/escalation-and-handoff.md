---
type: sop
audience: support_agent
version: 1.0
effective_date: 2026-01-01
---
# Escalation & Human Handoff

## When to hand off
Hand off when the customer explicitly asks for a person, when two consecutive automated attempts failed to resolve the issue, when there is a safety or account-security risk, when the case needs a payment decision outside the automated limits, or when the customer mentions legal action or a regulator.

## Handoff payload
The handoff must carry: the customer's goal, order number if known, facts already verified, solutions already attempted, the blocking point, and a suggested priority. Never present model guesses as verified facts.

## After handoff
Once a human agent accepts the conversation, the assistant stops replying; new messages go to the agent queue. The assistant resumes only after the agent submits a resolution.

## SLA targets
First human response: 15 minutes for safety or service-down cases, 1 hour for significant impact, 4 business hours for single-item issues, 1 business day for general questions.
