from retrieval.signals import exact_identifiers, inverse_document_frequency, rare_tokens


def test_exact_and_rare_signal_extraction():
    query = "Find CVIR-6360 on broker-17.prod.example.com with --retry-limit and ERR5029"

    identifiers = exact_identifiers(query)
    measured = rare_tokens(query)

    assert "CVIR-6360" in identifiers
    assert "broker-17.prod.example.com" in identifiers
    assert "--retry-limit" in identifiers
    assert {"cvir-6360", "broker-17.prod.example.com", "--retry-limit", "err5029"}.issubset(set(measured))


def test_inverse_document_frequency_rewards_rare_values():
    rare = inverse_document_frequency(100, 1)
    common = inverse_document_frequency(100, 80)

    assert rare > common > 1.0
