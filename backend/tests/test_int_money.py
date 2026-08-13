"""非负整型灵石/时限校验。"""

from __future__ import annotations

import pytest

from app.domain.int_money import require_non_negative_int
from app.schemas.social_trade import FaceTradeOfferRequest, FaceTradeVesselOffer


def test_require_non_negative_int_ok() -> None:
    assert require_non_negative_int(0, field_zh="灵石") == 0
    assert require_non_negative_int(12, field_zh="灵石") == 12
    assert require_non_negative_int(3.0, field_zh="灵石") == 3
    assert require_non_negative_int("42", field_zh="灵石") == 42


def test_require_non_negative_int_reject() -> None:
    with pytest.raises(ValueError):
        require_non_negative_int(-1, field_zh="灵石")
    with pytest.raises(ValueError):
        require_non_negative_int(1.5, field_zh="灵石")
    with pytest.raises(ValueError):
        require_non_negative_int(True, field_zh="灵石")
    with pytest.raises(ValueError):
        require_non_negative_int("1.2", field_zh="灵石")


def test_face_offer_schema_rejects_float_stones() -> None:
    with pytest.raises(Exception):
        FaceTradeOfferRequest(items=[], spirit_stones=1.5, version=1)
    with pytest.raises(Exception):
        FaceTradeVesselOffer(hours=2.5)
    ok = FaceTradeOfferRequest(items=[], spirit_stones=0, version=1)
    assert ok.spirit_stones == 0
    assert FaceTradeVesselOffer(hours=24).hours == 24
