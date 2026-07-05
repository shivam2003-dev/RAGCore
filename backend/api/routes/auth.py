from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.security import OAuth2PasswordRequestForm

from api.deps import AuthServiceDep, CurrentUser, require_role
from api.schemas import (
    ApiKeyCreatedResponse,
    ApiKeyCreateRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserOut,
)
from models import Role

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(body: RegisterRequest, auth: AuthServiceDep, request: Request) -> TokenResponse:
    _, pair = await auth.register(
        email=body.email,
        password=body.password,
        full_name=body.full_name,
        organization_name=body.organization_name,
        ip_address=request.client.host if request.client else None,
    )
    return TokenResponse(access_token=pair.access_token, refresh_token=pair.refresh_token)


@router.post("/login", response_model=TokenResponse)
async def login(
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    auth: AuthServiceDep,
    request: Request,
) -> TokenResponse:
    _, pair = await auth.login(
        email=form.username,
        password=form.password,
        ip_address=request.client.host if request.client else None,
    )
    return TokenResponse(access_token=pair.access_token, refresh_token=pair.refresh_token)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest, auth: AuthServiceDep) -> TokenResponse:
    pair = await auth.refresh(body.refresh_token)
    return TokenResponse(access_token=pair.access_token, refresh_token=pair.refresh_token)


@router.post("/logout", status_code=204)
async def logout(user: CurrentUser, auth: AuthServiceDep) -> None:
    await auth.logout(user)


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)


@router.post(
    "/api-keys",
    response_model=ApiKeyCreatedResponse,
    status_code=201,
    dependencies=[require_role(Role.ADMIN)],
)
async def create_api_key(
    body: ApiKeyCreateRequest, user: CurrentUser, auth: AuthServiceDep
) -> ApiKeyCreatedResponse:
    key, raw = await auth.create_api_key(user, body.name)
    return ApiKeyCreatedResponse(id=key.id, name=key.name, key=raw, key_prefix=key.key_prefix)
