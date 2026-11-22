import pickle

from disband import APIError, BusyError, NotFoundError, ServerError, WaitTimeoutError
from disband._errors import error_from_response
from disband._models import Problem, separation_adapter
from tests.fake import separation

problem_json = {"content-type": "application/problem+json"}


def problem(type_: str, status: int) -> bytes:
    return Problem(type=type_, title="Title", status=status, request_id="req").model_dump_json().encode()


def test_a_type_this_release_doesnt_name_falls_back_to_its_statuss_class():
    assert isinstance(error_from_response(404, problem_json, problem("stem-gone", 404)), NotFoundError)
    assert isinstance(error_from_response(503, problem_json, problem("overloaded", 503)), ServerError)
    unnamed = error_from_response(418, problem_json, problem("teapot", 418))
    assert type(unnamed) is APIError
    assert unnamed.type == "teapot"


def test_a_response_without_problem_details_still_raises_by_status():
    error = error_from_response(502, {"content-type": "text/html"}, b"<html>bad gateway</html>")
    assert isinstance(error, ServerError)
    assert (error.type, str(error)) == (None, "HTTP 502")


def test_errors_survive_pickling_for_workers_that_pass_them_on():
    busy = error_from_response(429, {**problem_json, "retry-after": "7"}, problem("busy", 429))
    copy = pickle.loads(pickle.dumps(busy))
    assert isinstance(copy, BusyError)
    assert (copy.retry_after, copy.request_id, str(copy)) == (7.0, "req", str(busy))

    waited = pickle.loads(pickle.dumps(WaitTimeoutError(separation_adapter.validate_python(separation("queued")))))
    assert isinstance(waited, WaitTimeoutError)
    assert waited.separation.status == "queued"
