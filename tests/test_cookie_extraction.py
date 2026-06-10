"""Cookie paste tolerance: users paste full headers, DevTools rows, or bare values."""
from web.routes.settings import extract_cookie_value


def test_bare_value():
    assert extract_cookie_value("AQEDAxyz123", "li_at") == "AQEDAxyz123"


def test_name_equals_value():
    assert extract_cookie_value("li_at=AQEDAxyz123", "li_at") == "AQEDAxyz123"


def test_full_cookie_header():
    raw = "bcookie=v2; li_at=AQEDAxyz123; lidc=b=OB94"
    assert extract_cookie_value(raw, "li_at") == "AQEDAxyz123"


def test_devtools_row_paste():
    assert extract_cookie_value("li_at\tAQEDAxyz123\t.linkedin.com\t/", "li_at") == "AQEDAxyz123"


def test_quoted_value():
    assert extract_cookie_value('"li_at=AQEDAxyz123"', "li_at") == "AQEDAxyz123"


def test_wrong_structured_paste_refused():
    assert extract_cookie_value("bcookie=v2; lidc=b=OB94", "li_at") == ""


def test_empty():
    assert extract_cookie_value("   ", "li_at") == ""
