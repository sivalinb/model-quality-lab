"""Impression-level datasets. No labels are ever passed into serving features."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import csv
import json
import math
import re
import numpy as np

FEATURES = ("topic_affinity", "subtopic_affinity", "log_popularity", "history_depth", "title_overlap")
TOPICS = ("technology", "sports", "science", "culture")
WORDS = {
    "technology": "software platform cloud chip engineering compute",
    "sports": "running race team marathon training championship",
    "science": "research space discovery climate biology experiment",
    "culture": "music art film community heritage festival",
}


@dataclass(frozen=True)
class Article:
    id: str
    topic: str
    subtopic: str
    title: str


@dataclass
class Impression:
    id: str
    user: str
    time: float
    history: list[str]
    candidates: list[str]
    labels: list[int]

    @property
    def cohort(self) -> str:
        return "returning" if self.history else "new"


@dataclass
class Dataset:
    name: str
    provenance: str
    articles: dict[str, Article]
    train: list[Impression]
    validation: list[Impression]
    test: list[Impression]
    metadata: dict = field(default_factory=dict)

    def manifest(self) -> dict:
        # Hash the actual content used by the experiment, including targets and histories.
        content = {
            "articles": [(a.id, a.topic, a.subtopic, a.title) for a in sorted(self.articles.values(), key=lambda x: x.id)],
            "splits": {name: [(i.id, i.user, i.time, i.history, i.candidates, i.labels)
                              for i in getattr(self, name)] for name in ("train", "validation", "test")},
        }
        return {"name": self.name, "provenance": self.provenance,
                "fingerprint": sha256(json.dumps(content, sort_keys=True).encode()).hexdigest(),
                "impressions": {k: len(getattr(self, k)) for k in ("train", "validation", "test")},
                "train_end": max(i.time for i in self.train),
                "test_start": min(i.time for i in self.test), **self.metadata}

    def validate(self) -> None:
        if not self.train or not self.test:
            raise ValueError("Training and evaluation splits must both contain impressions")
        if max(i.time for i in self.train) >= min(i.time for i in self.test):
            raise ValueError("Temporal leakage: training must precede evaluation")
        split_ids = [set(i.id for i in getattr(self, k)) for k in ("train", "validation", "test")]
        if any(split_ids[a] & split_ids[b] for a, b in ((0, 1), (0, 2), (1, 2))):
            raise ValueError("An impression appears in multiple splits")
        for split in (self.train, self.validation, self.test):
            for i in split:
                if len(i.candidates) != len(set(i.candidates)) or len(i.labels) != len(i.candidates):
                    raise ValueError("Candidate identities must be unique and aligned with labels")
                if not set(i.labels) <= {0, 1} or not i.candidates:
                    raise ValueError("Expected nonempty candidates and binary impression labels")
                if any(c not in self.articles for c in i.candidates + i.history):
                    raise ValueError("Unknown article in impression")


def pseudonym(value: str) -> str:
    return sha256(("mql-lab:" + value).encode()).hexdigest()[:20]


def synthetic(seed: int = 42, train_n: int = 2200, test_n: int = 900) -> Dataset:
    """A disclosed preference simulator; it is not MIND and not business evidence."""
    rng = np.random.default_rng(seed)
    articles = {}
    for t, topic in enumerate(TOPICS):
        for n in range(90):
            aid = f"A{t}-{n:03d}"
            articles[aid] = Article(aid, topic, f"{topic}-{n % 3}", f"{WORDS[topic]} story {n}")
    ids = list(articles)
    quality = {a: float(rng.normal()) for a in ids}
    users = {}
    for u in range(320):
        topic = TOPICS[u % len(TOPICS)]
        pool = [a for a in ids if articles[a].topic == topic]
        history = [] if u % 4 == 0 else list(rng.choice(pool, size=12, replace=False))
        users[u] = (topic, history)

    def make(start: int, count: int) -> list[Impression]:
        out = []
        for n in range(start, start + count):
            u = int(rng.integers(0, 320))
            topic, history = users[u]
            candidates = list(rng.choice(ids, size=12, replace=False))
            utility = np.array([3.8 * (articles[a].topic == topic and bool(history)) + 0.35 * quality[a]
                                for a in candidates])
            prob = np.exp(utility - utility.max()); prob /= prob.sum()
            chosen = int(rng.choice(len(candidates), p=prob))
            out.append(Impression(f"synthetic-{n:06d}", pseudonym(str(u)), 1700000000.0 + n * 60,
                                  history[:], candidates, [int(k == chosen) for k in range(len(candidates))]))
        return out

    ds = Dataset("seeded-news", "synthetic preference simulator; real model training and measured inference",
                 articles, make(0, train_n), make(train_n, 300), make(train_n + 300, test_n),
                 {"seed": seed, "labels": "simulated clicks", "counterfactual_claims": False})
    ds.validate()
    return ds


def load_mind(train_dir: Path, dev_dir: Path, train_limit: int = 8000, test_limit: int = 1800) -> Dataset:
    """Read official MIND TSVs. Keep each complete impression and its candidate set."""
    articles = {}
    for directory in (train_dir, dev_dir):
        with (directory / "news.tsv").open(encoding="utf-8") as f:
            for row in csv.reader(f, delimiter="\t"):
                if len(row) >= 4:
                    articles[row[0]] = Article(row[0], row[1] or "unknown", row[2] or "unknown", row[3])

    def read(directory: Path, prefix: str) -> list[Impression]:
        result = []
        with (directory / "behaviors.tsv").open(encoding="utf-8") as f:
            for row in csv.reader(f, delimiter="\t"):
                if len(row) < 5:
                    continue
                timestamp = datetime.strptime(row[2], "%m/%d/%Y %I:%M:%S %p").replace(tzinfo=timezone.utc).timestamp()
                pairs = [s.rsplit("-", 1) for s in row[4].split()]
                # Unlabeled test files are rejected; never interpret missing labels as negatives.
                if not pairs or any(len(p) != 2 or p[1] not in ("0", "1") for p in pairs):
                    raise ValueError("MIND requires labeled train/dev behaviors, not unlabeled test predictions")
                if any(p[0] not in articles for p in pairs):
                    continue
                # Duplicate candidates are invalid input, rather than silently changing the task.
                if len({p[0] for p in pairs}) != len(pairs):
                    continue
                result.append(Impression(prefix + row[0], pseudonym(row[1]), timestamp,
                                         [h for h in row[3].split() if h in articles],
                                         [p[0] for p in pairs], [int(p[1]) for p in pairs]))
        return sorted(result, key=lambda i: (i.time, i.id))

    raw_train = read(train_dir, "train-")
    dev = read(dev_dir, "dev-")
    if len(raw_train) < 50:
        raise ValueError("At least 50 labeled training impressions are required")
    cutoff = raw_train[int(len(raw_train) * .8)].time
    train = [i for i in raw_train if i.time < cutoff][-train_limit:]
    validation = [i for i in raw_train if i.time >= cutoff][:max(100, train_limit // 5)]
    # Evaluation is disjoint and chronologically later, even for nonstandard local MIND exports.
    training_end = max(x.time for x in raw_train)
    test = [i for i in dev if i.time > training_end][:test_limit]
    ds = Dataset("MIND-small", "Microsoft News public research dataset; historical impression replay",
                 articles, train, validation, test,
                 {"source": "https://msnews.github.io/", "labels": "recorded historical clicks",
                  "timestamp_assumption": "MIND timestamps parsed in a common UTC frame; source timezone unspecified",
                  "counterfactual_claims": False, "train_limit": train_limit, "test_limit": test_limit})
    ds.validate()
    return ds


class FeatureBuilder:
    """Train-only statistics + the request's past history. Explicit serving schema."""
    def __init__(self, ds: Dataset):
        self.articles = ds.articles
        self.clicks = Counter()
        for impression in ds.train:
            self.clicks.update(a for a, label in zip(impression.candidates, impression.labels) if label)
        self.train_ids = frozenset(i.id for i in ds.train)

    def build(self, impression: Impression) -> np.ndarray:
        history = [self.articles[a] for a in impression.history]
        topics = Counter(a.topic for a in history)
        subtopics = Counter(a.subtopic for a in history)
        words = set(re.findall(r"\w+", " ".join(a.title.lower() for a in history)))
        rows = []
        for aid in impression.candidates:
            a = self.articles[aid]
            tokens = set(re.findall(r"\w+", a.title.lower()))
            rows.append([topics[a.topic] / max(1, len(history)),
                         subtopics[a.subtopic] / max(1, len(history)),
                         math.log1p(self.clicks[aid]), math.log1p(len(history)),
                         len(words & tokens) / max(1, len(tokens))])
        return np.array(rows, dtype=float)

    def reference(self, impressions: list[Impression]) -> np.ndarray:
        return np.concatenate([self.build(i) for i in impressions])
