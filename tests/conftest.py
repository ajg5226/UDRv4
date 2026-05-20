import sys
from types import SimpleNamespace


class SessionState(dict):
    """Minimal Streamlit session state stub for auth unit tests."""


streamlit_stub = SimpleNamespace(session_state=SessionState())
sys.modules.setdefault("streamlit", streamlit_stub)
