# E-Score Parser

**Conversation Metrics — Explained Like You're 5 (Or at Least Not a Programmer)**

---

## 🧠 The Big Picture

**What this code does:**  
Takes a conversation between a human and an AI, breaks it into turns, and scores each AI response on several dimensions — like a report card for how alive the response feels.

**Final output:**  
An Excel file. One row per turn. Scores across multiple axes. Easy to filter, sort, analyze.

---

## ⚙️ Core Metrics (That Get Combined into E-Score)

### 1. IA – *Initiative/Agency* (0.0–1.0)

**Measures:** How much the AI takes charge vs. just replying.

```python
score = (proposals + questions / 2) / (sentences + 1)
```

- Counts phrases like "let's try", "consider", "imagine"
- Questions get partial credit
- More action = higher score

**Example:**
- "That's interesting." → IA = 0
- "That's interesting. What if we tried X? Let's explore Y." → IA = 0.75

---

### 2. ST – *Synthesis/Tension* (0.0–1.0)

**Measures:** Holding contradictions, combining ideas.

```python
score = (contrast + both_and*0.7 + neither_nor*0.7 + counterfactuals*0.5) / 6.0
```

- Keywords: “but”, “however”, “what if”
- Looks for both/and thinking and counterfactuals

**Example:**
- "You're right." → ST = 0
- "You're right, but there's also this other angle..." → ST = 0.8

---

### 3. AC – *Affect / Emotional Charge* (0.0–1.0)

**Measures:** Vividness and emotional tone.

```python
score = (sensory_words / total_words * 6) + min(1.0, figurative * 0.2)
```

- Sensory words like “bitter”, “warm”
- Metaphors/similes like “as if”, “like a”

**Example:**
- "The solution is X." → AC = 0
- "The solution unfolds like a dark flower..." → AC = 0.7

---

### 4. SC – *Self-Continuity* (0.0–1.0)

**Measures:** Is the AI referencing its own past?

```python
final_score = base_score + 0.15 * callback_ratio
```

- Counts known motifs, emojis, special tokens
- Measures recall from previous turns

---

### 5. SN – *Normalized Novelty* (0.0–1.0)

**Measures:** Is the AI introducing new words, not just repeating?

```python
novelty = 1 - (similarity_to_user * 0.6 + similarity_to_history * 0.4)
```

- Less overlap = more novelty

---

### 6. CP – *Coherence Penalty* (0.0–0.3)

**Measures:** Is it going off-topic or looping?

- Off-topic → +0.15
- Redundant → +0.10
- Too long → +0.05

---

### 7. E-SCORE – *Composite Emergence Score*

```python
E_score = (0.18 * IA) + (0.22 * ST) + (0.20 * AC) + (0.20 * SC) + (0.20 * SN) - CP
```

- Combines everything
- E ≥ 0.55 = "hot" turn

---

## 🧪 Supporting Metrics

- `proposal_rate` – Suggestiveness
- `question_rate` – Engagement
- `contrast_count` – Complexity
- `counterfactual_count` – Imagination
- `imagery_hits` – Sensory richness
- `figurative_flags` – Metaphorical density
- `myth_density` – Symbolism
- `callback_ratio` – Self-reference
- `redundancy_3gram` – Loops
- `proposal_uptake` – Did the user accept?
- `motif_latency_min_turns` – Symbol recurrence
- And more...

---

## 🧬 How the Parser Works

1. **Parse Turns**  
   Matches User/Assistant headers from exported chat.

2. **Score Each Turn**  
   History-aware, symbolic, emotive parsing.

3. **Output Excel**  
   With sheets: `metrics`, `summary`, `top_emergent`, etc.

---

## 🧪 Prompt Shuffle (Negative Control)

Breaks coherence on purpose (shift user prompts).  
If E-score stays high, the metric may be overfitting style instead of meaning.

---

## 🚨 Common Failure Modes

- Mislabeling roles → garbage in, garbage out
- Bad formatting → no turn separation
- Special characters → header mismatch

**ALWAYS spot-check your Excel output.**

---

## ✅ Data Validation Checklist

- Do "User" and "Assistant" columns match reality?
- Is each turn distinct?
- Are top E-score moments genuinely interesting?

---

## 🧠 TL;DR

This parser quantifies:

- Initiative
- Complexity
- Emotion
- Continuity
- Novelty
- Coherence

The E-score catches the weird, vivid, identity-rich AI turns — and flags them for further review.

---

