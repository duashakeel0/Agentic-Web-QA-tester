from app.domains import manifest
from app.domains.manifest import load_domains, save_workflow, slugify
from app.domains.schema import ExpectedOutcome, Workflow


def test_slugify_normalizes_to_lowercase_underscore():
    assert slugify("My New Site") == "my_new_site"
    assert slugify("  Already_slug  ") == "already_slug"
    assert slugify("Weird!!Chars??") == "weird_chars"
    assert slugify("") == "domain"


def test_save_workflow_creates_a_new_domain_file(tmp_path, monkeypatch):
    # save_workflow only normalizes the domain name (it doubles as the
    # filename) - the workflow itself is saved exactly as the caller built
    # it, since main.py's endpoint is what slugifies a workflow's name
    # before constructing it.
    monkeypatch.setattr(manifest, "DATA_DIR", tmp_path)
    workflow = Workflow(
        name="do_the_thing", steps=["Navigate to /x", "Click the Thing button"],
        expected_outcome=ExpectedOutcome(text_contains="Done"),
    )

    domain = save_workflow("My New Site", "https://example.com", workflow)

    assert domain.name == "my_new_site"
    assert (tmp_path / "my_new_site.yaml").exists()
    reloaded = load_domains()
    assert len(reloaded) == 1
    assert reloaded[0].workflows[0].name == "do_the_thing"


def test_save_workflow_appends_a_second_workflow_to_an_existing_domain(tmp_path, monkeypatch):
    monkeypatch.setattr(manifest, "DATA_DIR", tmp_path)
    save_workflow(
        "my_site", "https://example.com",
        Workflow(name="login", steps=["Log in"], expected_outcome=ExpectedOutcome(text_contains="Welcome")),
    )

    save_workflow(
        "my_site", "https://ignored.example.com",
        Workflow(name="checkout", steps=["Check out"], expected_outcome=ExpectedOutcome(text_contains="Order placed")),
    )

    domains = load_domains()
    assert len(domains) == 1
    assert domains[0].base_url == "https://example.com"  # base_url from the first save, not overwritten
    assert {w.name for w in domains[0].workflows} == {"login", "checkout"}


def test_save_workflow_replaces_a_workflow_with_the_same_name(tmp_path, monkeypatch):
    monkeypatch.setattr(manifest, "DATA_DIR", tmp_path)
    save_workflow(
        "my_site", "https://example.com",
        Workflow(name="login", steps=["Old step"], expected_outcome=ExpectedOutcome(text_contains="Welcome")),
    )

    save_workflow(
        "my_site", "https://example.com",
        Workflow(name="login", steps=["New step"], expected_outcome=ExpectedOutcome(text_contains="Welcome")),
    )

    domains = load_domains()
    assert len(domains[0].workflows) == 1
    assert domains[0].workflows[0].steps == ["New step"]


def test_load_domains_returns_all_registered_domains():
    domains = load_domains()
    names = {d.name for d in domains}
    assert {"parabank", "practice_software_testing", "campushub", "automation_exercise"} <= names


def test_every_domain_has_at_least_one_workflow():
    for domain in load_domains():
        assert len(domain.workflows) > 0
        assert domain.base_url.startswith("http")


def test_every_workflow_has_steps_and_an_expected_outcome():
    for domain in load_domains():
        for workflow in domain.workflows:
            assert len(workflow.steps) > 0
            assert workflow.expected_outcome.url_contains or workflow.expected_outcome.text_contains
