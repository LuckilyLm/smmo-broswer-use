from fastapi import APIRouter


def create_router() -> APIRouter:
    return APIRouter(tags=["campaigns"])
