import re
import difflib
import string
import pandas as pd

def highlight_text(text, term, termx):
    if not isinstance(text, str) or not text:
        return ""

    # Escape terms to prevent regex errors (e.g., if user types special characters like '?')
    words = [re.escape(w) for w in term.split() if w.strip()]
    wordsx = [re.escape(w) for w in termx.split() if w.strip()]

    if not words and not wordsx:
        return text

    # Build named groups for a single-pass regex to avoid HTML tag corruption
    patterns = []
    if words:
        words.sort(key=len, reverse=True)
        patterns.append(f"(?P<green>{'|'.join(words)})")
    if wordsx:
        wordsx.sort(key=len, reverse=True)
        patterns.append(f"(?P<red>{'|'.join(wordsx)})")

    combined_pattern = re.compile("|".join(patterns), re.IGNORECASE)

    def replace_match(m):
        if m.group("green"):
            return f'<span style="background-color: #98df8a; color: black; font-weight: normal; padding: 0px 0px; border-radius: 1px;">{m.group(0)}</span>'
        elif m.group("red"):
            return f'<span style="background-color: #ff9896; color: black; font-weight: normal; padding: 0px 0px; border-radius: 1px;">{m.group(0)}</span>'
        return m.group(0)

    return combined_pattern.sub(replace_match, text)


def normalize_doi(doi):
    """Normalize DOI string by stripping URLs, spaces, and lowercasing."""
    if pd.isna(doi):
        return None
    s = str(doi).strip().lower()
    # Strip URL prefixes if present
    for prefix in ["https://doi.org/", "http://doi.org/", "https://dx.doi.org/", "http://dx.doi.org/"]:
        if s.startswith(prefix):
            s = s[len(prefix):]
    s = s.strip()
    return s if s and s not in ["nan", "none", "[doi unavailable]"] else None


def normalize_title(title):
    """Normalize title for comparison: lowercase, strip punctuation and whitespace."""
    if pd.isna(title) or not isinstance(title, str):
        return ""
    # Lowercase and remove punctuation
    t = title.lower()
    t = t.translate(str.maketrans("", "", string.punctuation))
    return " ".join(t.split())


def find_doi_duplicates(df):
    """
    Finds row indices of duplicate papers by DOI (keeping the first occurrence).
    Returns a list of duplicate indices to drop.
    """
    if "DOI" not in df.columns:
        return []
    
    normalized = df["DOI"].apply(normalize_doi)
    # Mask valid (non-null) DOIs
    valid_mask = normalized.notna()
    
    # Identify duplicated valid DOIs (keep='first' marks 2nd+ occurrences as True)
    dup_mask = valid_mask & normalized.duplicated(keep="first")
    return df[dup_mask].index.tolist()


def find_title_duplicates(df, threshold=0.88):
    """
    Find pairs of papers suspected to be duplicates based on title similarity.
    Uses an exact-match pass followed by an inverted-index candidate search
    so duplicates are detected regardless of their row positions in the CSV.
    Skips pairs that already share an identical valid DOI (handled in DOI check).
    Returns a list of dicts: [{'idx_a': i, 'idx_b': j, 'score': int(similarity * 100)}]
    """
    if "Title" not in df.columns or df.empty:
        return []

    titles_clean = df["Title"].apply(normalize_title).tolist()
    norm_dois = (
        df["DOI"].apply(normalize_doi).tolist()
        if "DOI" in df.columns
        else [None] * len(df)
    )
    df_indices = df.index.tolist()
    n = len(titles_clean)
    pairs = []
    seen_pairs = set()

    def same_valid_doi(pos_a, pos_b):
        d_a, d_b = norm_dois[pos_a], norm_dois[pos_b]
        return d_a is not None and d_b is not None and d_a == d_b

    # Pass 1: Exact matches on normalized title
    title_to_pos = {}
    for pos, t in enumerate(titles_clean):
        if len(t) < 10:  # Ignore trivial/empty titles
            continue
        if t in title_to_pos:
            for first_pos in title_to_pos[t]:
                if same_valid_doi(first_pos, pos):
                    continue
                first_idx = df_indices[first_pos]
                orig_idx = df_indices[pos]
                pair_key = (min(first_idx, orig_idx), max(first_idx, orig_idx))
                if pair_key not in seen_pairs:
                    pairs.append({"idx_a": first_idx, "idx_b": orig_idx, "score": 100})
                    seen_pairs.add(pair_key)
            title_to_pos[t].append(pos)
        else:
            title_to_pos[t] = [pos]

    # Pass 2: Fuzzy match across all rows using an inverted word index
    word_to_positions = {}
    title_words = []
    for pos, t in enumerate(titles_clean):
        if len(t) < 15:
            title_words.append(set())
            continue
        words = {w for w in t.split() if len(w) >= 4}
        title_words.append(words)
        for w in words:
            word_to_positions.setdefault(w, []).append(pos)

    for i in range(n):
        t_i = titles_clean[i]
        words_i = title_words[i]
        if not words_i:
            continue

        candidate_counts = {}
        for w in words_i:
            for j in word_to_positions[w]:
                if j > i:
                    candidate_counts[j] = candidate_counts.get(j, 0) + 1

        min_shared = 1 if len(words_i) <= 3 else 2
        orig_i = df_indices[i]

        for j, shared in candidate_counts.items():
            if shared < min_shared:
                continue
            if same_valid_doi(i, j):
                continue
            orig_j = df_indices[j]
            pair_key = (min(orig_i, orig_j), max(orig_i, orig_j))
            if pair_key in seen_pairs:
                continue

            t_j = titles_clean[j]
            len_ratio = len(t_i) / max(len(t_j), 1)
            if len_ratio < 0.75 or len_ratio > 1.25:
                continue

            sim = difflib.SequenceMatcher(None, t_i, t_j).ratio()
            if sim >= threshold:
                pairs.append({"idx_a": orig_i, "idx_b": orig_j, "score": int(sim * 100)})
                seen_pairs.add(pair_key)

    return pairs