"""Loads every registered domain from data/*.yaml into validated Domain
objects. Adding a new domain means adding one new file here - nothing in
this module or the agents that use it needs to change.
"""

import re
from pathlib import Path

import yaml

from app.domains.schema import Domain, Workflow

DATA_DIR = Path(__file__).parent / "data"
_SLUG_PATTERN = re.compile(r"[^a-z0-9]+")


def load_domains() -> list[Domain]:
    domains = []
    for path in sorted(DATA_DIR.glob("*.yaml")):
        with open(path) as f:
            raw = yaml.safe_load(f)
        domains.append(Domain(**raw))
    return domains


def slugify(raw: str) -> str:
    """Normalizes a human-typed domain/workflow name into the same
    lowercase_underscore identifier style every registered domain already
    uses - both this store's existing convention, and necessary because a
    domain's name doubles as its YAML filename below."""
    slug = _SLUG_PATTERN.sub("_", raw.strip().lower()).strip("_")
    return slug or "domain"


def save_workflow(domain_name: str, base_url: str, workflow: Workflow) -> Domain:
    """Adds one workflow to a domain - creating the domain's YAML file if
    it's new, or appending/replacing the named workflow if the domain
    already exists. This is the write side of the same domain knowledge
    store load_domains() reads, so a dashboard "add domain knowledge"
    feature never has to touch a YAML file by hand - and a run against
    what it just wrote works immediately, since the Planner always reads
    the manifest fresh off disk rather than caching it."""
    name = slugify(domain_name)
    existing = next((d for d in load_domains() if d.name == name), None)

    if existing is not None:
        workflows = [w for w in existing.workflows if w.name != workflow.name] + [workflow]
        domain = Domain(name=existing.name, base_url=existing.base_url, workflows=workflows)
    else:
        domain = Domain(name=name, base_url=base_url, workflows=[workflow])

    path = DATA_DIR / f"{domain.name}.yaml"
    with open(path, "w") as f:
        yaml.safe_dump(domain.model_dump(mode="json"), f, sort_keys=False, allow_unicode=True)
    return domain
