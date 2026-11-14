"""
Pseudonymization of organization data (GDPR Art. 4(5), data protection by design, Art. 25).

People are replaced by keyed pseudonyms, HMAC-SHA256 of their id with a secret key, so the
reports show the structure of the organization without identifying anyone. With the same
key the pseudonyms are stable across runs, which keeps snapshots comparable; without the
key they cannot be reversed by trying likely ids (GitHub logins and e-mail addresses are
easy to guess, so an unkeyed hash would not protect them).

Only fields on an allow-list are kept: names, roles and free-text evidence are removed, and
known ids are replaced in the remaining text (coverage gaps, risk acceptance reasons).
Whoever holds the key and the original file can re-identify a pseudonym with
``hrg pseudonyms``; keep the key with the data protection officer or a secret store.
"""

import hashlib
import hmac
import os
import re
import secrets
from dataclasses import replace
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

PREFIX = "P-"
LENGTH = 8  # hex digits; colliding pseudonyms in one organization get more
KEY_ENV = "HRG_PSEUDONYM_KEY"
MIN_KEY_LENGTH = 16

PERSON_KEYS = ("id", "criticality", "last_active", "source", "confirmed")
DEPENDENCY_KEYS = ("from", "to", "type", "weight", "review", "source", "confirmed")
FUNCTION_KEYS = (
    "id", "name", "criticality", "requires", "separation", "performers", "alone", "source",
    "confirmed",
)  # fmt: skip
COVERAGE_KEYS = ("source", "branch", "pull_requests", "review_required", "gaps", "repositories")


class PseudonymKeyError(ValueError):
    pass


def load_key(key_file: Optional[Path] = None) -> Optional[bytes]:
    """The key from ``key_file`` or the HRG_PSEUDONYM_KEY environment variable, or None."""
    if key_file is not None:
        raw = Path(key_file).read_text(encoding="utf-8").strip()
        where = str(key_file)
    else:
        raw = os.environ.get(KEY_ENV, "").strip()
        where = KEY_ENV
        if not raw:
            return None
    if len(raw) < MIN_KEY_LENGTH:
        raise PseudonymKeyError(
            f"{where}: the pseudonym key must be at least {MIN_KEY_LENGTH} characters; "
            'generate one with: python -c "import secrets; print(secrets.token_hex(32))"'
        )
    return raw.encode("utf-8")


class Pseudonymizer:
    """Maps person ids to pseudonyms and removes identifying fields from organization data."""

    def __init__(self, key: Optional[bytes] = None):
        self.stable = key is not None
        self.key = key if key is not None else secrets.token_bytes(32)
        self.mapping: Dict[str, str] = {}
        self.aliases: Dict[str, str] = {}  # display names -> pseudonym, for free text

    def _digest(self, person_id: str) -> str:
        return hmac.new(self.key, person_id.encode("utf-8"), hashlib.sha256).hexdigest()

    def learn(self, ids: Iterable[str]) -> Dict[str, str]:
        """Pseudonyms for ``ids``, unique within everything learned so far."""
        for pid in sorted(set(ids) - set(self.mapping)):
            digest, length = self._digest(pid), LENGTH
            taken = set(self.mapping.values())
            while PREFIX + digest[:length] in taken:
                length += 4
            self.mapping[pid] = PREFIX + digest[:length]
        return self.mapping

    def person(self, pid: str) -> str:
        return self.mapping.get(pid, pid)

    def scrub(self, text: str) -> str:
        """Replace every known id and name in free text by its pseudonym."""
        words = {**self.aliases, **self.mapping}
        if not words or not text:
            return text
        ordered = sorted(words, key=len, reverse=True)
        # Only letters and digits bound a match: anna-org.yaml must lose "anna" too.
        pattern = re.compile(
            r"(?<![^\W_])@?(" + "|".join(re.escape(w.lstrip("@")) for w in ordered) + r")(?![^\W_])"
        )

        def swap(match: "re.Match[str]") -> str:
            found = match.group(0)
            return words.get(found) or words.get(match.group(1)) or found

        return pattern.sub(swap, text)

    def organization(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """A copy of an organization with pseudonymous people and no free-text evidence."""
        people = data.get("people") or []
        self.learn(p["id"] for p in people)
        for p in people:
            name = str(p.get("name") or "").strip()
            if name and name != p["id"]:
                self.aliases[name] = self.person(p["id"])
        out: Dict[str, Any] = {
            "people": [
                {
                    **{k: p[k] for k in PERSON_KEYS if k in p},
                    "id": self.person(p["id"]),
                    "name": self.person(p["id"]),
                }
                for p in people
            ],
            "dependencies": [
                {
                    **{k: d[k] for k in DEPENDENCY_KEYS if k in d},
                    "from": self.person(d["from"]),
                    "to": self.person(d["to"]),
                }
                for d in data.get("dependencies") or []
            ],
        }
        if data.get("functions") is not None:
            out["functions"] = [
                {
                    **{k: f[k] for k in FUNCTION_KEYS if k in f},
                    **{
                        key: [self.person(p) for p in f.get(key) or []]
                        for key in ("performers", "alone")
                        if key in f
                    },
                }
                for f in data["functions"]
            ]
        if isinstance(data.get("coverage"), dict):
            coverage = {k: data["coverage"][k] for k in COVERAGE_KEYS if k in data["coverage"]}
            for key in ("source", "branch"):
                if isinstance(coverage.get(key), str):
                    coverage[key] = self.scrub(coverage[key])
            for key in ("gaps", "repositories"):
                if key in coverage:
                    coverage[key] = [self.scrub(str(item)) for item in coverage[key] or []]
            out["coverage"] = coverage
        return out

    def target(self, target: Optional[str]) -> Optional[str]:
        """A risk acceptance target (person, ``from->to`` or function id) in pseudonyms."""
        if target is None:
            return None
        return "->".join(self.person(part) for part in target.split("->"))

    def acceptances(self, accept: List[Any]) -> List[Any]:
        return [
            replace(a, target=self.target(a.target), reason=self.scrub(a.reason)) for a in accept
        ]

    def table(self) -> List[Tuple[str, str]]:
        """(pseudonym, id) pairs for re-identification, sorted by pseudonym."""
        return sorted((p, i) for i, p in self.mapping.items())
