# Task 3: Justification

I chose database-level access control with Row Level Security because congressional documents can vary widely in sensitivity. Prompt instructions alone are not enough for security; the safer design is to prevent the agent from retrieving restricted chunks in the first place. This means the model is not asked to "ignore" classified or privileged material because that material never enters its context unless the user has permission.

The biggest failure mode is an overconfident plain-language translation that accidentally changes the legal meaning of a clause. To reduce that risk, the system preserves defined legal terms, flags nuance warnings, requires citations to retrieved text, and uses a confidence label when cross-references or definitions are missing. A human staff review step is still needed before publishing explanations to constituents or using them in official communications.

This design reflects the readings by treating AI as a decision-support tool rather than an authority. Following Hao's warning about the risks of trusting AI systems that hide uncertainty, the agent is required to cite sources, expose missing information, and say when confidence is low. The architecture also reflects the course emphasis on secure, auditable systems: access control happens before retrieval, and audit logs record which documents supported each answer.
