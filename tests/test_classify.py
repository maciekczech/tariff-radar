from tariff_radar.classify import classify_status, is_tariff_relevant


def test_customs_tariff_change_is_relevant() -> None:
    assert is_tariff_relevant("Government raises import tariffs", "A 25% customs duty applies")


def test_trade_remedy_is_relevant() -> None:
    assert is_tariff_relevant("Anti-dumping duty imposed", "Final determination on steel")


def test_utility_tariff_is_not_relevant() -> None:
    assert not is_tariff_relevant("Pipeline tariff filing", "Natural gas transmission rate")


def test_conference_without_measure_is_not_relevant() -> None:
    assert not is_tariff_relevant("Trade conference", "Panel discussion about global commerce")


def test_mfn_and_customs_levy_changes_are_relevant() -> None:
    assert is_tariff_relevant("Country changes MFN rates", "New rates apply to imported goods")
    assert is_tariff_relevant("Government abolishes customs levy", "The import charge ends today")


def test_study_mentioning_customs_duty_is_not_a_change() -> None:
    assert not is_tariff_relevant("New customs duty study published", "Researchers discuss policy")


def test_procedural_statuses_are_not_flattened_to_announced() -> None:
    assert classify_status("Preliminary antidumping determination") == "preliminary"
    assert classify_status("Initiation of safeguard investigation") == "investigation"
    assert classify_status("Final antidumping duty order") == "final"
    assert (
        classify_status("Final affirmative determination", "countervailing investigation")
        == "final"
    )
    assert classify_status("Revocation of countervailing duties") == "revoked_or_terminated"
