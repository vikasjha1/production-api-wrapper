from fastapi import APIRouter, Depends

from app.api.deps import AuthenticatedClient, get_current_client

router = APIRouter()


@router.get("/me")
def read_current_client(
    client: AuthenticatedClient = Depends(get_current_client),
) -> dict[str, str]:
    return {"client_id": client.client_id}
