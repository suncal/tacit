from fastapi import Request

from ..app import TacitApp


def get_app(request: Request) -> TacitApp:
    return request.app.state.tacit
