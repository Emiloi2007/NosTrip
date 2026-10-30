import pytest

from yt2tiktok.models import Segment, Word


def make_segment(start: float, text: str, wps: float = 3.0) -> Segment:
    words, t = [], start
    for w in text.split():
        words.append(Word(t, t + 1 / wps * 0.9, w))
        t += 1 / wps
    return Segment(start, t, text, words)


@pytest.fixture
def segments():
    sentences = [
        "Est-ce que vous saviez que les pieuvres ont trois cœurs ?",
        "C'est vrai, et leur sang est bleu à cause du cuivre.",
        "Elles peuvent aussi changer de couleur en une fraction de seconde.",
        "Leur cerveau est réparti dans leurs huit bras.",
        "Chaque bras peut goûter ce qu'il touche !",
        "Bref, ce sont des animaux incroyables.",
    ] * 4
    segs, t = [], 0.0
    for s in sentences:
        seg = make_segment(t, s)
        segs.append(seg)
        t = seg.end + 0.3
    return segs
