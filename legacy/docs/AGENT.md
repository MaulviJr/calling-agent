# Ava Engineering Rules

- Prefer simple readable code over clever abstractions.
- Keep the project a modular monolith.
- Do not invent API behavior.
- Verify current provider APIs before changing integrations.
- Never let the LLM invent calendar availability or business facts.
- Keep provider-specific logic isolated.
- Update ARCHITECTURE.md and DATA_FLOW.md after every milestone.
- Add comments explaining architectural reasons, not obvious syntax.
- Do not expose secrets.
- Preserve working functionality unless there is a clear reason to replace it.