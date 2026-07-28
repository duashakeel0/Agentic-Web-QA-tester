"""Loads every registered domain from data/*.yaml into validated Domain
objects. Adding a new domain means adding one new file here - nothing in
this module or the agents that use it needs to change.
"""

from pathlib import Path

import yaml

from app.domains.schema import Domain

DATA_DIR = Path(__file__).parent / "data"


def load_domains() -> list[Domain]:
    domains = []
    for path in sorted(DATA_DIR.glob("*.yaml")):
        with open(path) as f:
            raw = yaml.safe_load(f)
        domains.append(Domain(**raw))
    return domains
