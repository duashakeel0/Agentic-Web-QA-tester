from app.domains.manifest import load_domains


def test_load_domains_returns_all_registered_domains():
    domains = load_domains()
    names = {d.name for d in domains}
    assert {"sauce_demo", "the_internet", "campushub", "amazon"} <= names


def test_every_domain_has_at_least_one_workflow():
    for domain in load_domains():
        assert len(domain.workflows) > 0
        assert domain.base_url.startswith("http")


def test_every_workflow_has_steps_and_an_expected_outcome():
    for domain in load_domains():
        for workflow in domain.workflows:
            assert len(workflow.steps) > 0
            assert workflow.expected_outcome.url_contains or workflow.expected_outcome.text_contains
