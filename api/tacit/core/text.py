"""Text normalisation + similarity. Deliberately dependency-free and explainable —
a trust score you can't explain is a trust score nobody will act on."""
import re
from collections import Counter

_URL = re.compile(r"https?://\S+")
_MENTION = re.compile(r"[@#]\w[\w./-]*")
_NUM = re.compile(r"\b\d[\d,.:%-]*\b")
_TOKEN = re.compile(r"[a-z0-9][a-z0-9'-]{1,}")
STOP = set("""a an the and or but if then so of to in on at for by with from as is are was were be been being
this that these those it its i you we they he she them us our your their my me him her not no yes do does did
have has had will would can could should may might just also very really there here what which who whom when
where why how all any some each more most other such only own same than too s t can will don ve ll re d m
please thanks thank hi hello hey ok okay sure fyi cc re""".split())


def normalize(text: str) -> str:
    t = (text or "").lower()
    t = _URL.sub(" <url> ", t)
    t = _MENTION.sub(" <ref> ", t)
    t = _NUM.sub(" <num> ", t)
    return re.sub(r"\s+", " ", t).strip()


def tokens(text: str) -> list[str]:
    return [w for w in _TOKEN.findall(normalize(text)) if w not in STOP and not w.isdigit()]


def shingles(text: str, n: int = 2) -> set[str]:
    toks = tokens(text)
    if len(toks) < n:
        return set(toks)
    return {" ".join(toks[i:i + n]) for i in range(len(toks) - n + 1)} | set(toks)


def jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def similarity(a: str, b: str) -> float:
    """Blend of bigram/unigram overlap and length agreement. 0..1."""
    ta, tb = tokens(a), tokens(b)
    uni = jaccard(set(ta), set(tb))
    bi = jaccard(shingles(a), shingles(b))
    la, lb = max(len(ta), 1), max(len(tb), 1)
    length = min(la, lb) / max(la, lb)
    return round(0.5 * uni + 0.3 * bi + 0.2 * length, 4)


def keywords(texts: list[str], min_df: float = 0.6, limit: int = 6) -> list[str]:
    """Tokens present in at least min_df of the texts — the 'signature' of a trigger."""
    if not texts:
        return []
    df: Counter = Counter()
    for t in texts:
        for w in set(tokens(t)):
            df[w] += 1
    n = len(texts)
    out = [w for w, c in df.most_common() if c / n >= min_df and w not in ("<url>", "<ref>", "<num>")]
    return out[:limit]


def template(texts: list[str]) -> str:
    """The most central text of a cluster (medoid) — what a human would recognise as 'the usual reply'."""
    if not texts:
        return ""
    best, best_s = texts[0], -1.0
    sh = [shingles(t) for t in texts]
    for i, t in enumerate(texts):
        s = sum(jaccard(sh[i], sh[j]) for j in range(len(texts)) if j != i)
        if s > best_s:
            best, best_s = t, s
    return best


def stem(word: str) -> str:
    """Just enough to stop a plural from hiding a fact: invoices→invoice, policies→policy, resets→reset."""
    for suffix, repl in (("ies", "y"), ("sses", "ss"), ("ches", "ch"), ("shes", "sh"), ("xes", "x")):
        if len(word) > len(suffix) + 1 and word.endswith(suffix):
            return word[: -len(suffix)] + repl
    if len(word) > 3 and word.endswith("s") and not word.endswith(("ss", "us", "is")):
        return word[:-1]
    return word


def stems(text: str) -> set[str]:
    return {stem(t) for t in tokens(text)}
