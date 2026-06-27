from workgraph.adapters import filesystem


def _handler(sink):
    return filesystem._Handler(actor="me", sink=sink)


def test_debounce_collapses_a_burst_into_one_event(tmp_path):
    # macOS/watchdog fires create + modify + metadata for a single save; with a
    # path-based id these would otherwise become three EDITED events.
    f = tmp_path / "doc.txt"
    f.write_text("x")
    events = []
    h = _handler(events.append)

    h._emit(str(f), now=100.0)
    h._emit(str(f), now=100.05)
    h._emit(str(f), now=100.1)

    assert len(events) == 1
    assert events[0].type == "EDITED"
    assert events[0].duration is None  # first edit has no prior gap


def test_edit_after_window_emits_again_with_gap_duration(tmp_path):
    f = tmp_path / "doc.txt"
    f.write_text("x")
    events = []
    h = _handler(events.append)

    h._emit(str(f), now=100.0)        # save 1
    h._emit(str(f), now=100.05)       # debounced echo of save 1
    h._emit(str(f), now=130.0)        # save 2, well past the window

    assert len(events) == 2
    # duration of save 2 is the gap to the *emitted* save 1, not the sub-second echo
    assert events[1].duration == 30.0


def test_atomic_write_temp_files_are_ignored(tmp_path):
    # Editors/git write a temp file then rename it onto the real file; its real
    # suffix is a pid/hash, so it must be filtered by pattern, not suffix.
    junk = [
        "README.md.tmp.81653.55d8ac376359",  # atomic write
        "notes.txt~",                         # emacs backup
        ".#notes.txt",                        # emacs lock
        "~$report.docx",                      # Office lock
        "page.html.crswap",                   # crswap
    ]
    for n in junk:
        assert filesystem._ignored(tmp_path / n), f"should ignore {n}"
    # real files still pass through
    for n in ["README.md", "Q2-strategy.docx", "notes.txt"]:
        assert not filesystem._ignored(tmp_path / n), f"should keep {n}"


def test_distinct_paths_are_debounced_independently(tmp_path):
    a, b = tmp_path / "a.txt", tmp_path / "b.txt"
    a.write_text("a")
    b.write_text("b")
    events = []
    h = _handler(events.append)

    h._emit(str(a), now=100.0)
    h._emit(str(b), now=100.1)  # different path -> not debounced against a

    assert len(events) == 2
    assert {e.title for e in events} == {"a.txt", "b.txt"}
