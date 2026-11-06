"""
Guard against numbers "from thin air" in the agent's replies.

Every number in a final reply must be traceable to something real: a tool result (simulation table, summary,
plan, checker defaults), the user's own messages, or a simple derived value of the run results (difference or
percentage change between two results, or a unit scaling by 1000). Numbers that match nothing are reported as
unverified; the agent then asks the model once to rewrite, and flags whatever is still unverified.
"""
import bisect, json, math, re

# numbers that are not part of an identifier (W1, FL-2, SEP_3, run_2024...), a path or a version string
NUM = re.compile(r"(?<![\w./\\])(?<![A-Za-z_]-)[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?:[eE][-+]?\d+)?(?![\d_/\\]|\.\d)")
# not checked at all: code spans, file paths and run folder names (20261104-141216-136)
SKIP = re.compile(r"`[^`]*`|\S*[\\/]\S*|\b\d{6,}(?:-\d+)+\b")
GUIDANCE_MARK = "[Guidance for the assistant"
SMALL = 10          # small integers (counts, list numbers, "2 wells") are not checked
REL_TOL = 0.005     # 0.5 %


def _to_float(tok):
    try:
        return float(tok.replace(",", ""))
    except ValueError:
        return None


def numbers_in_text(text):
    """[(token, value, followed_by_percent)] for every checkable number in a piece of text."""
    out = []
    for line in SKIP.sub(" ", str(text)).splitlines():
        stripped = line.lstrip()
        for m in NUM.finditer(line):
            tok = m.group(0)
            # list markers "1." / "2)" at the start of a line
            if m.start() == len(line) - len(stripped) and line[m.end():m.end() + 1] in (".", ")"):
                continue
            v = _to_float(tok)
            if v is not None and math.isfinite(v):
                pct = bool(re.match(r"\s?(%|percent)", line[m.end():m.end() + 9]))
                out.append((tok, v, pct))
    return out


def numbers_in(obj, acc=None):
    """All numbers in a JSON-like object, including numbers written inside its strings."""
    acc = [] if acc is None else acc
    if isinstance(obj, bool) or obj is None:
        return acc
    if isinstance(obj, (int, float)):
        if math.isfinite(obj):
            acc.append(float(obj))
    elif isinstance(obj, str):
        acc.extend(v for _, v, _ in numbers_in_text(obj))
    elif isinstance(obj, dict):
        for k, v in obj.items():
            numbers_in(k, acc)
            numbers_in(v, acc)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            numbers_in(v, acc)
    return acc


def user_text(content):
    """The user's own words: drop the recipe guidance the agent appends (its numbers are placeholders)."""
    return str(content).split(GUIDANCE_MARK)[0]


def table_columns(table):
    """The run "table" is a list of 'a | b | c' strings (header first): numeric cells per column."""
    rows = [str(r).split(" | ") for r in table or []][1:]
    cols = {}
    for r in rows:
        for i, cell in enumerate(r):
            v = _to_float(cell.strip())
            if v is not None and math.isfinite(v):
                cols.setdefault(i, []).append(v)
    return list(cols.values()), [[_to_float(c.strip()) for c in r] for r in rows]


class Ledger:
    """Numbers known to be real in one conversation. Survives history compaction."""

    def __init__(self):
        self.known = set()
        # what an engineer computes from a run: differences between cases of the same result column (diffs), and
        # % changes between them or a value's share of another value in the same row (pcts, only for "x %")
        self.diffs, self.pcts = set(), set()

    def add_user(self, text):
        self.known.update(v for _, v, _ in numbers_in_text(user_text(text)))

    def add_result(self, name, result):
        self.known.update(numbers_in(result))
        if name != "run_study" or not isinstance(result, dict):
            return
        cols, rows = table_columns(result.get("table"))
        for col in cols:
            for i, a in enumerate(col):
                for b in col[i + 1:]:
                    self.diffs.add(abs(a - b))
                    for den in (a, b):
                        if den:
                            self.pcts.add(abs(a - b) / abs(den) * 100)
        for r in rows:
            vals = [abs(v) for v in r if isinstance(v, float) and v]
            for a in vals:
                for b in vals:
                    if a < b:
                        self.pcts.add(a / b * 100)

    @staticmethod
    def _tolerance(tok, v):
        """Half a unit of the last shown digit (rounded display); 'about 420' may stand for 415-425."""
        t = tok.replace(",", "").lstrip("+-")
        if "e" in t.lower():
            return abs(v) * REL_TOL
        if "." in t:
            step = 10 ** -len(t.split(".")[1])
        else:
            zeros = len(t) - len(t.rstrip("0")) if len(t) >= 3 else 0
            step = 10 ** min(zeros, 1)
        return max(step / 2, abs(v) * REL_TOL)

    @staticmethod
    def _near(v, tol, pool):
        lo, hi = bisect.bisect_left(pool, (v - tol) / (1 + REL_TOL)), bisect.bisect_right(pool, (v + tol) / (1 - REL_TOL))
        return any(abs(v - k) <= max(tol, k * REL_TOL) for k in pool[lo:hi])

    def unverified(self, text):
        """Numbers in text that match nothing known. Returns the tokens as written."""
        todo = [(tok, abs(v), pct) for tok, v, pct in numbers_in_text(text)
                if not (abs(v) <= SMALL and float(v).is_integer())]
        if not todo:
            return []
        known = sorted({abs(k) * f for k in self.known for f in (1.0, 1e3, 1e-3, 1e6, 1e-6)})
        diffs, pcts = sorted(self.diffs), sorted(self.pcts)
        bad = []
        for tok, v, pct in todo:
            tol = self._tolerance(tok, v)
            if self._near(v, tol, known) or self._near(v, tol, diffs) or (pct and self._near(v, tol, pcts)):
                continue
            bad.append(tok)
        return list(dict.fromkeys(bad))


def rewrite_note(bad):
    return ("(system note) Your reply contains numbers that are not in any tool result or user message: "
            + ", ".join(bad) + ". Rewrite the reply. Use only numbers that appear in the tool results (the run "
            "\"table\" and \"summary\", the plan, the checker) or that the user gave. If a number you wanted is not "
            "there, leave it out or say it was not calculated. Do not call tools.")


def flag_line(bad):
    return ("\n\n_Number check: " + ", ".join(bad) + " could not be traced to a simulation result or to your "
            "input; treat them with caution._")


if __name__ == "__main__":
    import sys
    led = Ledger()
    for path in sys.argv[2:]:
        led.add_result("run_study", json.load(open(path)))
    print(led.unverified(open(sys.argv[1]).read()))
