from app.core.masking import mask


def test_mask():
    assert mask("acct_demo_101") == "acct_***101"
    assert mask("short") == "short"