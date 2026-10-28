# 🚀 Autonomous Open-Source Issue Resolver Agent

> **Author**: [@mukeshsinghms0209-ai](https://github.com/mukeshsinghms0209-ai) | **Repository**: [mukeshsinghms0209-ai/mukesh-s-first](https://github.com/mukeshsinghms0209-ai/mukesh-s-first/tree/hackathon-agent)  
> **Hacktoberfest Hackathon Submission**: A local-first, privacy-preserving AI Agent that autonomously triages GitHub *Good First Issues* and produces verified patch code using Google's **Gemma** via **Ollama** and a modular **Agent Skills (`.skill.md`)** architecture.

---

## 🌟 Why This Wins
1. **100% Local-First & Zero Cloud Dependency**: Runs completely offline on edge hardware via Ollama and Gemma 2. No OpenAI API keys, zero data leakage, zero API bills.
2. **Modular `.skill.md` Architecture**: Skills are cleanly isolated into declarative Markdown files with YAML frontmatter. Adding new agent capabilities is as simple as dropping a new `.skill.md` file into `skills/`.
3. **Turnkey Open-Source Workflow**: Takes raw GitHub issue text -> Performs structured bug analysis -> Generates ready-to-apply unified `git diff` patch and `pytest` regression tests.

---

## 📁 Project Architecture

```
open-source-hackathon/
├── skills/
│   ├── issue-reader.skill.md    # Skill 1: Triage & technical decomposition
│   └── code-fixer.skill.md      # Skill 2: Patch generation & git diff builder
├── data/
│   └── sample_issue.json        # Test case: Real-world Good First Issue
├── output/                      # Auto-generated pipeline artifacts
│   ├── issue_analysis.json      # Structured diagnosis from Skill 1
│   ├── fix_report.md            # Maintainer explanation & test case
│   └── patch.diff               # Clean git-applyable unified diff
├── agent.py                     # Zero-dependency Python orchestrator
├── requirements.txt             # Optional dependencies
└── README.md                    # Project documentation & pitch guide
```

---

## ⚡ Quickstart Guide

### 1. Ensure Ollama and Gemma are Ready
Install [Ollama](https://ollama.com) and pull Google Gemma 2:
```bash
ollama run gemma2:2b "Hello"
```

### 2. Run the Autonomous Agent
Execute the agent against the sample Good First Issue:
```bash
python agent.py --model gemma2:2b
```

### 3. Check Generated Fix Artifacts
Inspect the generated patch in the `output/` directory:
```bash
# View unified git patch
cat output/patch.diff

# Or on Windows PowerShell:
Get-Content output/patch.diff
```

---

## 🎯 Modular Skills Concept
Each skill in `skills/*.skill.md` encapsulates:
- **YAML Frontmatter**: Defines `name`, `description`, and model hyperparameters (`temperature`, `top_p`).
- **System Instructions**: Defines persona, triage methodology, and deterministic JSON or Diff output schemas.
- **Dynamic Loading**: `agent.py` automatically discovers, validates, and chains skills at runtime.
