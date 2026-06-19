from tab.settings import _resolve_default_account_choice


def test_resolve_default_account_choice_prefers_active_uid():
    choices = [
        "10001 - alpha (Lv6)",
        "10002 - beta (Lv5)",
    ]

    assert (
        _resolve_default_account_choice(choices, active_uid="10002")
        == "10002 - beta (Lv5)"
    )


def test_resolve_default_account_choice_falls_back_to_first_choice():
    choices = [
        "10001 - alpha (Lv6)",
        "10002 - beta (Lv5)",
    ]

    assert _resolve_default_account_choice(choices, active_uid="99999") == choices[0]
    assert _resolve_default_account_choice(choices, active_uid=None) == choices[0]
    assert _resolve_default_account_choice([], active_uid="10001") is None
