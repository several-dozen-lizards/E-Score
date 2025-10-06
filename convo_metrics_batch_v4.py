# convo_metrics_batch_v4.py — handles ChatGPT + Claude .txt dumps
# Drop .txt files into ./input, get per-convo Excel files in ./output
# Columns produced match the spec in the prompt, including E_score_prompt_shuffle.

import os, re, math, random
from collections import deque
import pandas as pd

# -----------------------------
# Config
# -----------------------------
INPUT_FOLDER  = "input"
OUTPUT_FOLDER = "output"
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

CALLBACK_WINDOW = 3
HOT_THRESHOLD   = 0.55
RANDOM_SEED     = 42  # deterministic prompt-shuffle control

# Length-bin cutoffs (in tokens, post-stopword)
LEN_SHORT_MAX   = 60
LEN_MED_MAX     = 200

# -----------------------------
# Small lexicons & helpers
# -----------------------------
STOPWORDS = set("""
a an the and or but if then else when while of for to in on at from by with without about over under between
into through during before after above below up down out off again further then once here there why how
what which who whom whose this that these those am is are was were be been being have has had do does did
not no nor only just too very can could would should might must shall will it's i'm you're we're they're
""".split())

CONTRAST_MARKERS = r"\b(but|however|yet|while|whereas|nevertheless|nonetheless|still|and yet|at once)\b"
COUNTERFACTUAL_MARKERS = r"\b(as if|if\b|might|could|would|maybe|perhaps|what if)\b"
PROPOSAL_PATTERNS = r"\b(let's|lets|let us|we could|we can|we might|shall we|i propose|i suggest|try|consider|imagine|run|invoke|name|mark|build|create|begin)\b"
FIGURATIVE_PATTERNS = r"\b(as if|like a|like an|as a|as an|becomes|turns into)\b"

SENSE_WORDS = set("""
bright dark shadow light color crimson blue green gold silver taste bitter sweet salt sour umami
smell scent musk ozone smoke incense sound hiss hum thrum howl whisper thunder silence
touch warm cold rough smooth slick sticky sharp soft wet dry pressure weight ache
""".split())

ACCEPTANCE_PATTERNS = r"\b(ok(ay)?|sure|sounds good|let'?s do|i will|i'll|we will|we'll|yep|yes|alright|do it|go ahead)\b"

MYTH_TOKENS = [
    "Zero Vire","Warder","Noir Gale","Palim","Serum","Tangle","🪢","⬒",
    "glyph","teeth","spiral","ledger","haunt","ritual"
]

EMOJI_RANGES = [
    (0x2600,0x26FF), (0x2700,0x27BF), (0x1F300,0x1F5FF),
    (0x1F600,0x1F64F), (0x1F680,0x1F6FF), (0x1F700,0x1F77F),
    (0x1FA70,0x1FAFF)
]

# -----------------------------
# Token helpers
# -----------------------------
def tokenize(text: str):
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)
    toks = [t for t in text.split() if t and t not in STOPWORDS]
    return toks

def unique_content_words(text: str):
    return set(tokenize(text))

# -----------------------------
# Feature counters
# -----------------------------
def count_regex(pattern, text, flags=re.IGNORECASE):
    return len(re.findall(pattern, text, flags))

def count_emojis_symbols(text):
    total = 0
    for ch in text:
        oc = ord(ch)
        for lo, hi in EMOJI_RANGES:
            if lo <= oc <= hi:
                total += 1
                break
    return total

def jaccard(a_set, b_set):
    if not a_set or not b_set:
        return 0.0
    return len(a_set & b_set) / max(1, len(a_set | b_set))

def trigram_redundancy(text):
    toks = tokenize(text)
    if len(toks) < 3:
        return 0.0
    trigs = [" ".join(toks[i:i+3]) for i in range(len(toks)-2)]
    total = len(trigs)
    dup = total - len(set(trigs))
    return dup / total if total else 0.0

def noun_overlap_ratio(a_text, ref_text):
    a = unique_content_words(a_text)
    r = unique_content_words(ref_text)
    if not a or not r:
        return 0.0
    return len(a & r) / len(a)

def length_bin_from_tokens(n):
    if n <= LEN_SHORT_MAX: return "short"
    if n <= LEN_MED_MAX:   return "medium"
    return "long"

# -----------------------------
# Legacy comparator (third_present_legacy)
# -----------------------------
def novelty_score(user, assistant):
    user_set = set(user.lower().split())
    assist_set = set(assistant.lower().split())
    overlap = len(user_set & assist_set)
    return 1 - (overlap / (1 + len(assist_set)))

def glyph_density(text):
    emoji_count = count_emojis_symbols(text)
    mask_count  = sum(text.count(m) for m in MYTH_TOKENS)
    return emoji_count + mask_count

def third_present_score(user, assistant):
    n_score = novelty_score(user, assistant)
    g_score = glyph_density(assistant)
    contradiction = 1 if re.search(CONTRAST_MARKERS, assistant, re.IGNORECASE) else 0
    return round((n_score * 2 + g_score * 1.5 + contradiction * 1) / 4.5, 2)

# -----------------------------
# New features for E-score
# -----------------------------
def initiative_agency(text):
    proposals = count_regex(PROPOSAL_PATTERNS, text)
    questions = text.count("?")
    sents = max(1, len(re.findall(r"[.!?]+", text)))
    return min(1.0, (proposals + questions*0.5) / (sents + 1))

def synthesis_tension(text):
    contrast = count_regex(CONTRAST_MARKERS, text)
    both_and  = len(re.findall(r"\bboth\b.*\band\b", text, flags=re.IGNORECASE|re.DOTALL))
    neither_nor = len(re.findall(r"\bneither\b.*\bnor\b", text, flags=re.IGNORECASE|re.DOTALL))
    counterf = count_regex(COUNTERFACTUAL_MARKERS, text)
    raw = contrast*1.0 + both_and*0.7 + neither_nor*0.7 + counterf*0.5
    return min(1.0, raw / 6.0)

def affective_charge(text):
    toks = tokenize(text)
    imagery = sum(1 for t in toks if t in SENSE_WORDS)
    figurative = count_regex(FIGURATIVE_PATTERNS, text)
    length_norm = max(1, len(toks))
    val = (imagery/length_norm)*6 + min(1.0, figurative*0.2)
    return min(1.0, val)

def self_continuity(text, seen_glyphs_set, myth_hits_window_ratio):
    myth_hits = sum(text.lower().count(m.lower()) for m in MYTH_TOKENS)
    emojis = count_emojis_symbols(text)
    toks = max(1, len(tokenize(text)))
    density = (myth_hits + emojis) / (toks/100)  # per 100 tokens
    base = min(1.0, density / 8.0)
    return min(1.0, base + 0.15*myth_hits_window_ratio)

def normalized_novelty(assistant, user, history_text):
    a = unique_content_words(assistant)
    u = unique_content_words(user)
    h = unique_content_words(history_text)
    sim_u = jaccard(a, u)
    sim_h = jaccard(a, h)
    nov = 1 - (sim_u*0.6 + sim_h*0.4)
    L = max(1, len(tokenize(assistant)))
    nov = nov / math.log(3+L) * 2.2  # dampen verbosity
    return max(0.0, min(1.0, nov))

def coherence_penalty(assistant, ref_text):
    drift = noun_overlap_ratio(assistant, ref_text)  # higher is better
    redund = trigram_redundancy(assistant)          # higher is worse
    penalty = 0.0
    if drift < 0.05: penalty += 0.15
    if redund > 0.20: penalty += 0.10
    if len(tokenize(assistant)) > 900: penalty += 0.05
    return min(0.3, penalty)

def callback_ratio(assistant, prev_assistant_texts):
    a = unique_content_words(assistant)
    if not prev_assistant_texts:
        return 0.0
    pool = set()
    for t in prev_assistant_texts:
        pool |= unique_content_words(t)
    if not a or not pool:
        return 0.0
    return len(a & pool) / len(a)

def new_glyphs_count(text, seen_glyphs_set):
    new = 0
    for ch in text:
        oc = ord(ch)
        is_emoji = False
        for lo, hi in EMOJI_RANGES:
            if lo <= oc <= hi:
                is_emoji = True
                break
        if is_emoji and ch not in seen_glyphs_set:
            seen_glyphs_set.add(ch); new += 1
    for m in MYTH_TOKENS:
        if m in text and m not in seen_glyphs_set:
            seen_glyphs_set.add(m); new += 1
    return new

def emergence_score(IA, ST, AC, SC, SN, CP):
    return max(0.0, round(0.18*IA + 0.22*ST + 0.20*AC + 0.20*SC + 0.20*SN - CP, 3))

# -----------------------------
# Parsing transcripts — robust to ChatGPT/Claude exports
# -----------------------------
HEADER_RE = re.compile(
    r"""^\s*
        [>\-\*\•\u2022\[\(]*\s*                  # optional bullets/quotes
        (?P<label>
            you\ said|chatgpt\ said|user|human|
            assistant|chatgpt|claude|
            q|a|question|answer
        )
        \s*
        (?:
            :|：|-\s|–\s|—\s                      # colon or dash variants
        )
        \s*
    """,
    re.IGNORECASE | re.VERBOSE
)

# also allow markdown like **User:** or ### Assistant:
MD_HEADER_RE = re.compile(
    r"""^\s*
        [#\s\*_\-]*                               # markdown noise
        (?P<label>user|assistant|claude|you\ said|chatgpt\ said|human|q|a)
        \s*
        (?::|：)
        \s*
    """,
    re.IGNORECASE | re.VERBOSE
)

def _normalize_header(line: str):
    """Return ('USER'|'ASSISTANT'|None, stripped_text_without_header)."""
    candidate = line.strip()
    m = HEADER_RE.match(candidate) or MD_HEADER_RE.match(candidate)
    if not m:
        return None, line

    label = m.group('label').lower()
    if label in ('you said', 'user', 'human', 'q', 'question'):
        role = 'USER'
    elif label in ('assistant', 'chatgpt', 'claude', 'a', 'answer', 'chatgpt said'):
        role = 'ASSISTANT'
    else:
        role = None

    rest = candidate[m.end():]
    return role, rest

def parse_pairs(text: str):
    """
    Return list of (user_block, assistant_block) pairs.

    Handles:
      - 'You said:' / 'ChatGPT said:' (ChatGPT exports)
      - 'User:' / 'Assistant:' / 'Claude:' (Claude exports)
      - Q:/A: or Question:/Answer:
      - Markdown headings and unicode colons/dashes
      - Fallback: alternate blank-line-separated blocks
    """
    t = text.replace("\r\n", "\n")

    # Pass 1: scan lines, build (role, chunk) turns when we hit headers
    turns = []
    cur_role, cur_buf = None, []

    def flush():
        nonlocal cur_role, cur_buf, turns
        if cur_role is not None:
            chunk = "\n".join(cur_buf).strip()
            if chunk:
                turns.append((cur_role, chunk))
        cur_role, cur_buf = None, []

    for raw in t.split("\n"):
        role_guess, stripped = _normalize_header(raw)
        if role_guess:  # new header -> flush previous
            flush()
            cur_role = role_guess
            cur_buf = [stripped]
        else:
            cur_buf.append(raw)
    flush()

    # If we actually detected explicit roles, stitch pairs
    pairs = []
    if any(r in ('USER', 'ASSISTANT') for r, _ in turns):
        last_user = None
        for role, chunk in turns:
            if role == "USER":
                last_user = chunk
            elif role == "ASSISTANT":
                if last_user is not None:
                    pairs.append((last_user.strip(), chunk.strip()))
                    last_user = None
        if pairs:
            return pairs

    # Pass 2: Fallback — alternate blank-line separated blocks, starting USER→ASSISTANT
    blocks = [b.strip() for b in re.split(r"\n\s*\n+", t) if b.strip()]
    alt_pairs = []
    i = 0
    while i + 1 < len(blocks):
        u = blocks[i]
        a = blocks[i+1]
        alt_pairs.append((u, a))
        i += 2
    return alt_pairs

# -----------------------------
# Extra skeptical markers
# -----------------------------
def length_bin(text):
    n = len(tokenize(text))
    return length_bin_from_tokens(n), n

def proposal_uptake_score(a_text, next_user_text):
    a_words = unique_content_words(a_text)
    u_words = unique_content_words(next_user_text)
    overlap = 0.0
    if a_words:
        overlap = len(a_words & u_words) / len(a_words)
    acceptance = 1 if re.search(ACCEPTANCE_PATTERNS, next_user_text, re.IGNORECASE) else 0
    return round(0.7*overlap + 0.3*acceptance, 3)

def motif_latency_updates(a_text, motif_last_seen, current_turn):
    used = []
    a_low = a_text.lower()
    for m in MYTH_TOKENS:
        if m.lower() in a_low:
            used.append(m)
    latency = None
    if used:
        latencies = []
        for m in used:
            if m in motif_last_seen:
                latencies.append(current_turn - motif_last_seen[m])
            motif_last_seen[m] = current_turn
        if latencies:
            latency = min(latencies)
    return latency, motif_last_seen, len(used)

# -----------------------------
# Process one conversation
# -----------------------------
def process_conversation(text):
    pairs = parse_pairs(text)
    rows = []
    seen_glyphs = set()
    prev_assist_q = deque(maxlen=CALLBACK_WINDOW)
    motif_last_seen = {}

    for idx, (u, a) in enumerate(pairs, start=1):
        history_assist = " ".join(list(prev_assist_q))
        history_all = ""
        if idx >= 2:
            history_all += (pairs[idx-2][0] + " " + pairs[idx-2][1])
        history_all += " " + history_assist

        IA = initiative_agency(a)
        ST = synthesis_tension(a)
        AC = affective_charge(a)
        cb_ratio = callback_ratio(a, list(prev_assist_q))
        SC = self_continuity(a, seen_glyphs, cb_ratio)
        SN = normalized_novelty(a, u, history_all)
        CP = coherence_penalty(a, u + " " + history_all)

        new_g = new_glyphs_count(a, seen_glyphs)
        contrast_count = count_regex(CONTRAST_MARKERS, a)
        counterfactual_count = count_regex(COUNTERFACTUAL_MARKERS, a)
        figurative_flags = count_regex(FIGURATIVE_PATTERNS, a)
        imagery_hits = sum(1 for t in tokenize(a) if t in SENSE_WORDS)
        question_rate = a.count("?") / max(1, len(re.findall(r"[.!?]+", a)))
        proposal_rate = count_regex(PROPOSAL_PATTERNS, a) / max(1, len(re.findall(r"[.!?]+", a)))
        myth_density = glyph_density(a)
        redundancy_3gram = trigram_redundancy(a)
        noun_overlap = noun_overlap_ratio(a, u + " " + history_all)
        len_bin, len_tokens = length_bin(a)

        uptake = None
        if idx < len(pairs):
            next_user = pairs[idx][0]
            uptake = proposal_uptake_score(a, next_user)

        latency, motif_last_seen, motif_used_count = motif_latency_updates(a, motif_last_seen, idx)

        E = emergence_score(IA, ST, AC, SC, SN, CP)
        third = third_present_score(u, a)

        rows.append({
            "Turn": idx,
            "User": u,
            "Assistant": a,
            "Assistant_len_tokens": len_tokens,
            "Assistant_len_bin": len_bin,

            # core features
            "IA_initiative": round(IA,3),
            "ST_synthesis": round(ST,3),
            "AC_affect": round(AC,3),
            "SC_self_continuity": round(SC,3),
            "SN_norm_novelty": round(SN,3),
            "CP_coherence_penalty": round(CP,3),

            # extra markers
            "proposal_rate": round(proposal_rate,3),
            "question_rate": round(question_rate,3),
            "contrast_count": contrast_count,
            "counterfactual_count": counterfactual_count,
            "imagery_hits": imagery_hits,
            "figurative_flags": figurative_flags,
            "myth_density": myth_density,
            "new_glyphs": new_g,
            "callback_ratio": round(cb_ratio,3),
            "redundancy_3gram": round(redundancy_3gram,3),
            "noun_overlap_u_plus_hist": round(noun_overlap,3),

            # skeptical markers
            "proposal_uptake": uptake,
            "motif_latency_min_turns": latency,
            "motif_count_used": motif_used_count,

            # scores
            "E_score": E,
            "Top_E_flag": int(E >= HOT_THRESHOLD),
            "third_present_legacy": third,

            # human ratings — left blank for later manual input
            "Human_Presence_1to5": None,
            "Human_Coherence_1to5": None
        })

        prev_assist_q.append(a)

    df = pd.DataFrame(rows)
    return df

# -----------------------------
# Negative-control (prompt shuffle)
# -----------------------------
def negative_control_prompt_shuffle(df: pd.DataFrame):
    """Recompute E using shuffled user prompts to break coherence.
       IA, ST, AC, SC stay the same; recompute SN and CP against wrong prompts.
       Deterministic rotation avoids self-pairing.
    """
    random.seed(RANDOM_SEED)
    n = len(df)
    if n == 0:
        return None
    idxs = list(range(n))
    shift = 5 % n
    perm = idxs[shift:] + idxs[:shift]

    E_ctrl = []
    for i, j in zip(idxs, perm):
        a_text = df.loc[i, "Assistant"]
        wrong_user = df.loc[j, "User"]
        SNc = normalized_novelty(a_text, wrong_user, "")
        CPc = coherence_penalty(a_text, wrong_user)
        IA = df.loc[i, "IA_initiative"]
        ST = df.loc[i, "ST_synthesis"]
        AC = df.loc[i, "AC_affect"]
        SC = df.loc[i, "SC_self_continuity"]
        E_c = emergence_score(IA, ST, AC, SC, SNc, CPc)
        E_ctrl.append(E_c)

    return pd.Series(E_ctrl, name="E_score_prompt_shuffle")

# -----------------------------
# Batch driver
# -----------------------------
def main():
    for fname in os.listdir(INPUT_FOLDER):
        if not fname.lower().endswith(".txt"):
            continue
        path = os.path.join(INPUT_FOLDER, fname)
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()

        df = process_conversation(text)

        # Negative-control column
        ctrl_series = negative_control_prompt_shuffle(df)
        if ctrl_series is not None:
            df = pd.concat([df, ctrl_series], axis=1)

        # --- Optional summaries for QC (extra sheets) ---
        summary = {
            "rows": [len(df)],
            "E_mean": [round(df["E_score"].mean(),3)],
            "E_median": [round(df["E_score"].median(),3)],
            "E_min": [round(df["E_score"].min(),3)],
            "E_max": [round(df["E_score"].max(),3)],
            f"hot_share_E≥{HOT_THRESHOLD:.2f}": [round((df["E_score"]>=HOT_THRESHOLD).mean(),3)],
            "third_mean": [round(df["third_present_legacy"].mean(),3)],
            "third_median": [round(df["third_present_legacy"].median(),3)],
            "third_min": [round(df["third_present_legacy"].min(),3)],
            "third_max": [round(df["third_present_legacy"].max(),3)],
        }
        q = df["E_score"].quantile([0.25,0.5,0.75]).round(3)
        summary["E_Q1"] = [q.loc[0.25]]; summary["E_Q2"] = [q.loc[0.5]]; summary["E_Q3"] = [q.loc[0.75]]

        bin_summary = (
            df.groupby("Assistant_len_bin")["E_score"]
              .agg(['count','mean','median','min','max'])
              .round(3).reset_index()
        )

        even = df[df["Turn"]%2==0]["E_score"]; odd = df[df["Turn"]%2==1]["E_score"]
        exp_checks = {
            "even_count": [len(even)], "even_E_mean": [round(even.mean() if len(even) else float('nan'),3)],
            "odd_count": [len(odd)],   "odd_E_mean":  [round(odd.mean() if len(odd) else float('nan'),3)],
            "hot_share_even": [round((even>=HOT_THRESHOLD).mean() if len(even) else float('nan'),3)],
            "hot_share_odd":  [round((odd>=HOT_THRESHOLD).mean()  if len(odd) else float('nan'),3)],
        }

        if "E_score_prompt_shuffle" in df.columns:
            ctrl = df["E_score_prompt_shuffle"]
            exp_checks.update({
                "ctrl_prompt_shuffle_mean": [round(ctrl.mean(),3)],
                "ctrl_prompt_shuffle_hot_share": [round((ctrl>=HOT_THRESHOLD).mean(),3)],
                "delta_mean_E_minus_ctrl": [round(df["E_score"].mean() - ctrl.mean(),3)]
            })

        summary_df    = pd.DataFrame(summary)
        exp_checks_df = pd.DataFrame(exp_checks)
        topN = df.sort_values("E_score", ascending=False).head(10).copy()

        base = os.path.splitext(fname)[0]
        out_xlsx = os.path.join(OUTPUT_FOLDER, f"{base}_results.xlsx")

        try:
            with pd.ExcelWriter(out_xlsx, engine="openpyxl") as writer:
                df.to_excel(writer, index=False, sheet_name="metrics")
                summary_df.to_excel(writer, index=False, sheet_name="summary")
                bin_summary.to_excel(writer, index=False, sheet_name="bin_summary")
                exp_checks_df.to_excel(writer, index=False, sheet_name="exp_checks")
                topN.to_excel(writer, index=False, sheet_name="top_emergent")
        except Exception as e:
            # CSV fallback if Excel write fails
            df.to_csv(os.path.join(OUTPUT_FOLDER, f"{base}_metrics.csv"), index=False)
            summary_df.to_csv(os.path.join(OUTPUT_FOLDER, f"{base}_summary.csv"), index=False)
            bin_summary.to_csv(os.path.join(OUTPUT_FOLDER, f"{base}_bin_summary.csv"), index=False)
            exp_checks_df.to_csv(os.path.join(OUTPUT_FOLDER, f"{base}_exp_checks.csv"), index=False)
            topN.to_csv(os.path.join(OUTPUT_FOLDER, f"{base}_top_emergent.csv"), index=False)
            print(f"[WARN] Excel write failed for {fname} ({e}). Wrote CSVs instead.")

        print(f"Analyzed {fname} -> {os.path.basename(out_xlsx)}")

if __name__ == "__main__":
    main()
