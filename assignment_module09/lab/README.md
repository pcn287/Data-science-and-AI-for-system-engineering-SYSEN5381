# Module 09 lab — AI text quality control

This folder contains `text_quality_control_lab.py`, which scores the narrative in `data.txt` with four Likert dimensions (formality, clarity, succinctness, relevance), runs repeated checks via **Ollama** and/or **OpenAI**, compares runs to `manual_qc_scores.json`, and optionally runs Welch *t*-tests between providers.

**Run** (from this directory): `py text_quality_control_lab.py`  
Useful flags: `--ollama-only`, `--openai-only`, `--iterations N`, `--workers N`, `--parallel-providers`. Defaults favor a smaller local model (`smollm2:1.7b`) and configurable `OPENAI_TEMPERATURE`; CSV outputs are written here without dumping full tables to the console.

---

### iii. Brief explanation (lab write-up)

I designed the prompt around four qualities that fit a technical report—formality, clarity, succinctness, and relevance—and asked for answers in a fixed format so I could compare Ollama, OpenAI, and my own scores side by side; I only lightly adjusted how the lab was run (speed and what prints on screen), not the basic questions the model answers. Manual quality control is my own one-time judgment in `manual_qc_scores.json`, while AI quality control applies the same rubric automatically and can be repeated, which makes it easy to see when the models agree with me and when they do not. What worked well was getting fast, structured scores and a clear comparison to manual numbers; what I would improve next is adding plain-language examples for each score level in the prompt and reviewing disagreements more carefully so the rubric better matches what “good” means for this assignment.
