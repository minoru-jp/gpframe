
from gpframe.contracts.exceptions import UncheckedError

def test_initial_creation_requires_frame_name_and_error():
    err = UncheckedError("worker", ValueError("boom"))
    assert err.frame_name == "worker"
    assert isinstance(err.cause, ValueError)