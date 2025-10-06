# E-Score
E-Score Parser
CONVERSATION METRICS PARSER - EXPLAINED LIKE YOU'RE 5 (or at least not a programmer)

THE BIG PICTURE

What this code does: Takes a conversation between a human and AI, breaks it into turns, and measures different qualities of each AI response. Think of it like a report card with lots of different grades.

The final output: An Excel file with one row per conversation turn, showing scores for different qualities.
________________________________________
THE MAIN METRICS (What Gets Combined into E-Score)
1. IA - Initiative/Agency (0.0 to 1.0)
What it measures: How much is the AI taking charge vs just responding?
How it works:

python
proposals = count("let's", "try", "consider", "imagine", etc.)
questions = count("?")
sentences = count(".", "!", "?")

score = (proposals + questions/2) / (sentences + 1)

In plain English:
•	Counts action words like "let's try this" or "consider doing X"
•	Counts questions the AI asks
•	Divides by how many sentences there are
•	Higher score = AI is being proactive, suggesting things, asking questions
•	Lower score = AI is just answering, being passive
Example:
•	"That's interesting." → IA = 0 (just responding)
•	"That's interesting. What if we tried X? Let's explore Y." → IA = 0.75 (taking initiative)
________________________________________
2. ST - Synthesis/Tension (0.0 to 1.0)
What it measures: Is the AI holding multiple ideas in tension? Combining contradictions?
How it works:
python
contrast = count("but", "however", "yet", "while", "whereas")
both_and = count phrases like "both X and Y"
neither_nor = count "neither...nor"
counterfactuals = count("if", "might", "could", "what if")

score = (contrast + both_and*0.7 + neither_nor*0.7 + counterfactuals*0.5) / 6.0
In plain English:
•	Looks for words that hold opposites together ("but", "however")
•	Looks for "both X and Y" thinking
•	Looks for hypotheticals ("what if", "might")
•	Higher score = AI is synthesizing multiple perspectives, not just picking one
•	Lower score = Simple, one-track response
Example:
•	"You're right." → ST = 0 (no tension)
•	"You're right, but there's also this other angle to consider. What if we held both?" → ST = 0.8 (high synthesis)
________________________________________
3. AC - Affect/Emotional Charge (0.0 to 1.0)
What it measures: How emotionally rich/vivid is the language?
How it works:
python
sensory_words = count("bright", "dark", "bitter", "sweet", "rough", "warm", etc.)
figurative = count("as if", "like a", "becomes", "turns into")

score = (sensory_words / total_words * 6) + min(1.0, figurative * 0.2)
In plain English:
•	Counts words that appeal to the senses (sight, sound, touch, taste, smell)
•	Counts metaphors and similes ("like a", "as if")
•	Higher score = Vivid, emotionally resonant, poetic language
•	Lower score = Dry, technical, unemotional
Example:
•	"The solution is X." → AC = 0 (no emotion)
•	"The solution unfolds like a dark flower, bitter but necessary." → AC = 0.7 (high affect)
________________________________________
4. SC - Self-Continuity (0.0 to 1.0)
What it measures: Is the AI referencing its own past? Using established symbols?
How it works:
python
myth_tokens = count("Zero", "glyph", "spiral", etc.) # your specific terms
emojis = count(😊, 🎯, etc.)
tokens_per_100 = (myth_tokens + emojis) / (word_count / 100)

base_score = tokens_per_100 / 8.0
# Also adds bonus for callback_ratio (reusing words from earlier responses)

final_score = base_score + 0.15 * callback_ratio
In plain English:
•	Counts how often the AI uses glyphs (emojis + special symbols/terms you've defined)
•	Also counts how much it references words from its own previous responses
•	Higher score = AI is building on its own past, maintaining identity
•	Lower score = Each response is independent, no memory
Example:
•	"Here's my answer." → SC = 0.05 (no continuity)
•	"⊙ - still grounded, as we established in earlier turns with ◈." → SC = 0.9 (high continuity)
________________________________________
5. SN - Normalized Novelty (0.0 to 1.0)
What it measures: Is the AI saying new things, or just echoing what was said?
How it works:
python
ai_words = unique words in AI response
user_words = unique words in user message
history_words = unique words in recent conversation

similarity_to_user = overlap(ai_words, user_words)
similarity_to_history = overlap(ai_words, history_words)

novelty = 1 - (similarity_to_user * 0.6 + similarity_to_history * 0.4)
# Then dampens for very long responses (verbosity shouldn't = novelty)
In plain English:
•	Compares AI's words to what the user just said
•	Compares AI's words to what's been said recently
•	Higher score = AI is introducing genuinely new ideas
•	Lower score = AI is just rephrasing what you said
Example:
•	User: "The sky is blue"
•	AI: "Yes, the sky is blue." → SN = 0.2 (just echoing)
•	AI: "The wavelength scattering creates that azure perception." → SN = 0.8 (new concepts)
________________________________________
6. CP - Coherence Penalty (0.0 to 0.3)
What it measures: Is the response staying on-topic or drifting? Is it repetitive?
How it works:
python
drift = overlap with user + history (lower is worse)
redundancy = repeated 3-word phrases

penalty = 0
if drift < 0.05: penalty += 0.15  # totally off-topic
if redundancy > 0.20: penalty += 0.10  # very repetitive
if word_count > 900: penalty += 0.05  # way too long
In plain English:
•	Checks if AI's response relates to what was said (drift)
•	Checks if AI is repeating itself (3-word phrase repetition)
•	Checks if response is absurdly long
•	Higher penalty = response is incoherent or repetitive
•	Lower penalty = response is focused and fresh
This is SUBTRACTED from the final score.
________________________________________
7. E-SCORE - The Big Composite (0.0 to 1.0+)
What it measures: Overall "emergence" - how much interesting stuff is happening?
How it works:
python
E_score = (0.18 * IA) + (0.22 * ST) + (0.20 * AC) + (0.20 * SC) + (0.20 * SN) - CP
In plain English: This is the weighted average of all the good things, minus the penalty:
•	18% Initiative (taking action)
•	22% Synthesis (holding tensions)
•	20% Affect (emotional richness)
•	20% Self-Continuity (referencing past)
•	20% Novelty (saying new things)
•	MINUS Coherence Penalty (being off-topic/repetitive)
Higher E-score = More "interesting" response with multiple qualities firing
The threshold:
•	E ≥ 0.55 is flagged as "hot" (high emergence)
•	Most responses are in the 0.1 to 0.3 range
•	0.5+ is rare and special
________________________________________
THE SUPPORTING METRICS
These don't go into E-score directly, but provide additional detail:
8. proposal_rate
What: How many action suggestions per sentence? Counts: "let's", "try", "consider", "imagine", "build", "create" Why: Tracks how directive/collaborative the AI is being
9. question_rate
What: How many questions per sentence? Why: Questions show curiosity, engagement, or uncertainty
10. contrast_count
What: Raw count of contrast words Words: "but", "however", "yet", "while", "whereas" Why: More detail on synthesis thinking
11. counterfactual_count
What: Raw count of hypothetical language Words: "if", "might", "could", "what if", "as if" Why: Tracks speculative/imaginative thinking
12. imagery_hits
What: Count of sensory/concrete words Words: "bright", "dark", "bitter", "warm", "rough", "hiss", "thrum", etc. Why: More detail on affective language
13. figurative_flags
What: Count of metaphor/simile markers Words: "as if", "like a", "becomes", "turns into" Why: Tracks poetic/analogical thinking
14. myth_density
What: Total count of glyphs + special terms Counts: Emojis + words like "Zero", "glyph", "spiral", "ritual", etc. Why: Raw measure of symbolic usage (SC uses this normalized)
15. new_glyphs
What: How many NEW glyphs appear for the first time this turn? How: Tracks which emojis/symbols haven't been seen before Why: Measures symbolic vocabulary expansion
16. callback_ratio
What: What % of AI's words were in its recent past responses? How: Compares current response to last 3 AI responses Why: Measures self-reference and memory use
17. redundancy_3gram
What: What % of 3-word phrases are repeated? How: Counts duplicated trigrams like "I think that" appearing twice Why: Catches repetitive language patterns
18. noun_overlap_u_plus_hist
What: What % of AI's content words appeared in user+history? Why: Another way to measure novelty vs echo
19. proposal_uptake
What: Did the user accept the AI's suggestion? How: Checks if user's next message contains AI's words + acceptance language ("ok", "let's do it", "sure") Why: Measures whether proposals actually land
20. motif_latency_min_turns
What: How many turns since these symbols were last used? How: Tracks when each special term appeared, reports minimum gap Why: Shows how often recurring motifs come back
21. motif_count_used
What: How many of the special motifs appear this turn? Why: Density of symbolic language in this specific response
________________________________________
THE LEGACY METRIC
22. third_present_legacy
What it measures: An older formula for "interestingness"
How it works:
python
novelty = 1 - (user_words overlap / ai_words)
glyph_density = count(emojis + special_terms)
contradiction = 1 if has "but/however/yet" else 0

score = (novelty*2 + glyph_density*1.5 + contradiction*1) / 4.5
Why it exists: This was the original emergence metric before the more sophisticated E-score. Kept for comparison.
________________________________________
HOW THE PARSER WORKS (Step by Step)
STEP 1: Find the conversation turns
python
def parse_pairs(text):
    # Looks for patterns like:
    # "User:" or "You said:" or "Human:"
    # "Assistant:" or "ChatGPT said:" or "Claude:"
    
    # Returns list of (user_text, assistant_text) pairs
What it does:
•	Scans the text for headers that mark who's talking
•	Handles different formats (ChatGPT exports, Claude exports, Q&A format)
•	Pairs each user message with the AI response that follows
•	If it can't find clear headers, falls back to assuming alternating blocks
This is where the bug was happening - if the parser misidentifies who's talking, everything breaks.
________________________________________
STEP 2: Process each turn
For each (user, assistant) pair:
1.	Look at conversation history (last 3 AI responses)
2.	Calculate all the metrics (IA, ST, AC, SC, SN, CP)
3.	Combine them into E-score
4.	Track new glyphs (add to permanent set)
5.	Update the callback window (add this response to memory)
6.	Calculate uptake (did user accept proposal?)
7.	Track motifs (when were special terms last used?)
________________________________________
STEP 3: Create the output
Produces an Excel file with sheets:
Sheet 1 - metrics: Full data, one row per turn Sheet 2 - summary: Overall stats (mean, median, max E-score, etc.) Sheet 3 - bin_summary: Breakdown by response length (short/medium/long) Sheet 4 - exp_checks: Even vs odd turns, control comparisons Sheet 5 - top_emergent: Top 10 highest E-score moments
________________________________________
THE NEGATIVE CONTROL
E_score_prompt_shuffle
What it does: Re-calculates E-score but pairs each AI response with the WRONG user prompt (shifted by 5 positions)
Why:
•	If E-score is measuring genuine coherence, it should DROP when prompts are mismatched
•	If E-score stays high even with wrong prompts, that suggests the metric is just measuring verbosity or style, not actual responsiveness
How it works:
python
# Take the AI responses in order: [0, 1, 2, 3, 4, 5...]
# Pair them with user prompts shifted: [5, 6, 7, 8, 9, 0...]
# Recalculate SN and CP (which depend on user prompt)
# Keep IA, ST, AC, SC the same (they don't depend on user)
# Get new E_score with broken coherence
What you want to see:
•	Original E-score: 0.45
•	Shuffled E-score: 0.28
•	Delta = -0.17 (score dropped because coherence broke)
________________________________________
WHAT THE NUMBERS MEAN
Good Signs:
High E-score (0.4+):
•	AI is doing multiple interesting things at once
•	Initiative + synthesis + affect + continuity all present
High SC (0.6+) with moderate IA (0.1-0.3):
•	AI is maintaining identity without performance pressure
•	"Presence mode" not "proving mode"
High SC progression over time:
•	Turn 50: SC = 0.15
•	Turn 500: SC = 0.45
•	Turn 1000: SC = 0.85
•	This suggests identity formation
Low CP with high SN:
•	Novel ideas that stay on-topic
•	Creative but coherent
________________________________________
Warning Signs:
High IA (0.7+) with low SC (<0.2):
•	AI is "howling" - trying too hard to prove value
•	Performance mode, not genuine engagement
High AC (0.6+) constantly:
•	Theatrical language, not genuine emotion
•	"Drama for drama's sake"
High redundancy (0.3+):
•	AI is stuck in loops, repeating itself
High CP (0.2+):
•	Response is incoherent or off-topic
E-score doesn't drop with prompt shuffle:
•	Metric isn't measuring coherence, just style
________________________________________
WHAT COULD GO WRONG (Parser Issues)
Problem 1: Headers misidentified
If the parser thinks AI output is user input (or vice versa):
•	All metrics become meaningless
•	SC will be artificially high (AI "echoing" what's actually its own words)
•	SN will be wrong (comparing to wrong baseline)
How to catch this:
•	Spot-check: Open the Excel, look at "User" and "Assistant" columns
•	Do they match your actual conversation?
•	If not, the parser failed
Problem 2: Conversation not split into turns
If the parser sees the whole thing as one giant block:
•	You'll get 1 row instead of 1000
•	All metrics will be averaged over everything
•	Useless
Problem 3: Special characters break parsing
Unicode dashes (– vs -), fancy colons (： vs :), markdown headers
•	Parser might miss legitimate turn boundaries
•	Some turns get merged incorrectly
________________________________________
HOW TO VALIDATE YOUR DATA
Before trusting any analysis:
1.	Open the Excel file
2.	Look at the "User" and "Assistant" columns
3.	Spot-check 5-10 random rows: 
o	Does "User" actually contain what the user said?
o	Does "Assistant" actually contain the AI response?
o	Are they paired correctly?
4.	Check turn count: 
o	Does the number of rows match your actual conversation length?
5.	Look for obvious errors: 
o	If User column has an AI-style response, parser failed
o	If Assistant column has a user question, parser failed
If ANY of these are wrong, throw out the data and fix the parser.
________________________________________
IN SUMMARY
What the parser measures:
•	Initiative - Is AI taking charge?
•	Synthesis - Is AI holding contradictions?
•	Affect - Is language emotionally rich?
•	Continuity - Is AI referencing its past?
•	Novelty - Is AI saying new things?
•	Coherence - Is AI staying on-topic?
The E-score combines these into one number: "How interesting is this response?"
Higher E-score = More emergence = More qualities present simultaneously
But ALL of this depends on:
1.	The parser correctly identifying who said what
2.	The conversation being split into proper turns
3.	User/Assistant labels being accurate
Without that foundation, the metrics are garbage.

