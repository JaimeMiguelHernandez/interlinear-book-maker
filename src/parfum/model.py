"""The book.json contract. Every later stage reads this shape."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Iterator


def satz_id(teil: int, kapitel: int, sektion: int, satz: int) -> str:
    return f"T{teil}.K{kapitel:02d}.S{sektion:02d}.s{satz:03d}"


@dataclass(frozen=True)
class Satz:
    id: str
    text: str


@dataclass
class Sektion:
    id: str
    saetze: list[Satz] = field(default_factory=list)


@dataclass
class Kapitel:
    id: str
    number: int
    sektionen: list[Sektion] = field(default_factory=list)


@dataclass
class Teil:
    id: str
    number: int
    kapitel: list[Kapitel] = field(default_factory=list)


@dataclass
class Book:
    teile: list[Teil] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Book":
        return cls(teile=[
            Teil(id=t["id"], number=t["number"], kapitel=[
                Kapitel(id=k["id"], number=k["number"], sektionen=[
                    Sektion(id=s["id"], saetze=[Satz(**z) for z in s["saetze"]])
                    for s in k["sektionen"]
                ])
                for k in t["kapitel"]
            ])
            for t in data["teile"]
        ])

    def iter_sektionen(self) -> Iterator[Sektion]:
        for teil in self.teile:
            for kapitel in teil.kapitel:
                yield from kapitel.sektionen

    def iter_saetze(self) -> Iterator[Satz]:
        for sektion in self.iter_sektionen():
            yield from sektion.saetze
