from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class Word:
    start: float
    end: float
    text: str


@dataclass
class Segment:
    start: float
    end: float
    text: str
    words: list[Word] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> "Segment":
        return cls(d["start"], d["end"], d["text"], [Word(**w) for w in d.get("words", [])])


@dataclass
class Clip:
    start: float
    end: float
    title: str = ""
    description: str = ""
    hashtags: list[str] = field(default_factory=list)
    score: float = 0.0

    @property
    def duration(self) -> float:
        return self.end - self.start

    def to_dict(self) -> dict:
        return asdict(self)
