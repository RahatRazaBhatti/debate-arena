# AI Debate Arena - Project Specification

## 1. Project Overview

AI Debate Arena is a command-line application where two AI agents debate a topic provided by the user. A human moderator can guide the debate by asking questions, interrupting the discussion, or ending the debate. The system is built using LangGraph, LangChain, Groq LLM, and several custom tools.

---

# 2. Input

The application accepts a single debate topic from the user.

Example:

Should homework be banned?

---

# 3. Output

The application produces:

- Complete debate transcript
- Live momentum scoreboard
- Tool usage log
- Final debate summary

---

# 4. Actors

## Human Moderator

Responsibilities

- Starts the debate
- Interrupts the debate
- Asks questions
- Redirects discussion
- Ends the debate

---

## AI Agent 1

Name:

Elena

Role:

Evidence-first researcher

Characteristics

- Uses studies
- Uses statistics
- Uses factual evidence
- Logical reasoning

---

## AI Agent 2

Name:

Marcus

Role:

Practical systems thinker

Characteristics

- Real-world solutions
- Economic reasoning
- Cost-benefit analysis
- Practical arguments

---

# 5. Project Scope

This project includes

- Two AI debate agents
- LangGraph workflow
- Human moderator
- Custom tools
- Momentum scoring system
- Terminal user interface

---

# 6. Non-Goals

This version does NOT include

- User login
- Database
- Web interface
- Multiple debates running simultaneously
- Long-term memory between sessions

---

# 7. Technologies

- Python
- LangGraph
- LangChain
- Groq
- DuckDuckGo Search
- Rich
- Pydantic
- pytest

---

# 8. Future Enhancements

Possible future improvements

- Vector database (FAISS)
- RAG pipeline
- Multiple debate agents
- Web interface
- Persistent memory