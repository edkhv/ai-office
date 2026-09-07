"""Public token-gated setup and authenticated workspace administration."""

from fastapi import APIRouter, Depends, Request

from app import workspace
from app.workspace_contracts import Setup, UserCreate, UserUpdate


def make_workspace_router(actor_dependency, engine, settings, clock):
    router = APIRouter(prefix="/api/v1")

    @router.get("/setup/status")
    def setup_status():
        return workspace.status(engine, settings)

    @router.post("/setup", status_code=201)
    def setup(body: Setup, request: Request):
        return workspace.complete_setup(engine, settings, body, clock(), request.state.request_id)

    @router.get("/workspace")
    def info(who=Depends(actor_dependency)):
        return workspace.info(engine, who)

    @router.get("/users")
    def users(who=Depends(actor_dependency)):
        return workspace.list_users(engine, who)

    @router.post("/users", status_code=201)
    def create(body: UserCreate, request: Request, who=Depends(actor_dependency)):
        return workspace.create_user(engine, settings, who, body, clock(), request.state.request_id)

    @router.patch("/users/{actor_id}")
    def update(actor_id: str, body: UserUpdate, request: Request, who=Depends(actor_dependency)):
        return workspace.update_user(engine, who, actor_id, body, clock(), request.state.request_id)

    @router.post("/users/{actor_id}/credential")
    def credential(actor_id: str, request: Request, who=Depends(actor_dependency)):
        return workspace.rotate_credential(
            engine, settings, who, actor_id, clock(), request.state.request_id
        )

    return router
