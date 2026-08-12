"""道主 API Schema。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class DaoLordClaimRequest(BaseModel):
    """POST /dao-lord/claim。"""

    dao_id: str | None = Field(default=None, description="默认本命道")


class DaoContestRsvpRequest(BaseModel):
    """POST /dao-lord/contests/current/rsvp。"""

    accept: bool = Field(..., description="true=前往擂台；false=弃权（道主则为快照）")


class DaoContestArenaLeaveRequest(BaseModel):
    """POST /dao-lord/contests/current/arena/leave。

    是否判负由服务端根据场次状态决定，客户端不可关闭判负。
    """

    model_config = {"extra": "ignore"}
