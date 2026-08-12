"""角色相关 HTTP 路由（创建 / 获取我的角色）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.core.deps import get_character_service, get_current_user
from app.db.models import User
from app.schemas.character import CreateCharacterRequest
from app.schemas.common import success
from app.services.character_service import CharacterService, character_public_to_dict

router = APIRouter(prefix="/characters", tags=["characters"])


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=None,
)
async def create_character(
    payload: CreateCharacterRequest,
    characters: CharacterService = Depends(get_character_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """
    创建角色（需 Bearer；一账号一角色）。

    Args:
        payload: 仅含道号。
        characters: 角色应用服务。
        current_user: 当前登录用户。

    Returns:
        dict: 含完整 CharacterPublic 的统一信封。
    """
    public = await characters.create(current_user, payload)
    return success(character_public_to_dict(public))


@router.get("/me", response_model=None)
async def get_my_character(
    characters: CharacterService = Depends(get_character_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """
    获取当前账号的角色面板数据。

    Args:
        characters: 角色应用服务。
        current_user: 当前登录用户。

    Returns:
        dict: CharacterPublic 信封；无角色时业务码 ``40005``。
    """
    public = await characters.get_mine(current_user)
    return success(character_public_to_dict(public))
