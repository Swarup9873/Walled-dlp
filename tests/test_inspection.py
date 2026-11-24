from core.inspection import InspectionService, contains_marker


def make_service(answer=True):
    calls = []

    def confirm(kind, name):
        calls.append((kind, name))
        return answer

    return InspectionService(confirm), calls


def test_contains_marker_exact():
    assert contains_marker("hello WALLED_SENSITIVE world")
    assert not contains_marker("hello world")
    assert not contains_marker("walled_sensitive")  # exact match for typed text


def test_contains_marker_fuzzy_for_ocr():
    assert contains_marker("WALLED SENSITIVE", fuzzy=True)
    assert contains_marker("WAIIED_SENSITIVE", fuzzy=True)  # l -> I confusion
    assert not contains_marker("WALLED OTHER", fuzzy=True)


def test_clean_prompt_no_dialog():
    svc, calls = make_service()
    assert svc.review_prompt("what is the capital of France?") is True
    assert calls == []


def test_marker_prompt_continue_and_cancel():
    svc, calls = make_service(True)
    assert svc.review_prompt("please read WALLED_SENSITIVE data") is True
    assert calls[0][0] == "prompt"
    svc, _ = make_service(False)
    assert svc.review_prompt("WALLED_SENSITIVE") is False


def test_long_prompt_snippet_is_truncated():
    svc, calls = make_service()
    svc.review_prompt("WALLED_SENSITIVE " + "x" * 1000)
    assert len(calls[0][1]) <= 160


def test_file_dialog_gets_file_name():
    svc, calls = make_service(False)
    assert svc.review_file("secrets.txt", b"abc WALLED_SENSITIVE") is False
    assert calls == [("file", "secrets.txt")]


def test_clean_file_no_dialog():
    svc, calls = make_service()
    assert svc.review_file("notes.txt", b"nothing here") is True
    assert calls == []


def test_unscannable_file_fails_open():
    svc, calls = make_service(False)
    # Claims to be a PDF but is garbage: extraction errors -> allowed, no dialog.
    assert svc.review_file("broken.pdf", b"%PDF-1.4 garbage") is True
    assert calls == []
