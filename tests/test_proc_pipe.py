"""proc.py cross-platform runner: shell-free pipes + the {"write": (path, text)} pseudo-step.

The write-tuple shape matches the existing convention in annual_commands.py;
this suite pins that proc.run_sequence handles it natively (run = write the file, emit = render a
reproducible command), so callers no longer need a local _materialize_writes."""
import os
from hcl_core import proc


def test_pipe_is_byte_equivalent_and_shell_free(tmp_path):
    (tmp_path / "in.txt").write_text("3\n1\n2\n")
    steps = [{"cmd": ["cat", "in.txt", "|", "sort"], "stdout": "out.txt"}]
    res = proc.run_sequence(steps, str(tmp_path), True, unavailable_reason="x")
    assert res["returncode"] == 0
    assert (tmp_path / "out.txt").read_bytes() == b"1\n2\n3\n"


def test_pipe_nonzero_returncode_surfaces(tmp_path):
    # A failing stage in the pipe must be reported, not swallowed.
    steps = [{"cmd": ["cat", "no_such_file.txt", "|", "sort"], "stdout": "out.txt"}]
    res = proc.run_sequence(steps, str(tmp_path), True, unavailable_reason="x")
    assert res["returncode"] != 0


def test_write_tuple_creates_file_on_run(tmp_path):
    steps = [{"write": ("sky.rad", "void glow g\n0\n0\n4 1 1 1 0\n")}]
    res = proc.run_sequence(steps, str(tmp_path), True, unavailable_reason="x")
    assert res["returncode"] == 0
    assert (tmp_path / "sky.rad").read_bytes() == b"void glow g\n0\n0\n4 1 1 1 0\n"


def test_write_tuple_append(tmp_path):
    proc.run_sequence([{"write": ("a.txt", "one\n")}], str(tmp_path), True, unavailable_reason="x")
    proc.run_sequence([{"write": ("a.txt", "two\n"), "append": True}], str(tmp_path), True,
                      unavailable_reason="x")
    assert (tmp_path / "a.txt").read_bytes() == b"one\ntwo\n"


def test_write_tuple_uses_lf_even_with_crlf_text(tmp_path):
    # Generated Radiance text is normalized to LF regardless of the source string.
    steps = [{"write": ("m.rad", "void plastic m\r\n0\r\n")}]
    proc.run_sequence(steps, str(tmp_path), True, unavailable_reason="x")
    assert b"\r\n" not in (tmp_path / "m.rad").read_bytes()


def test_write_tuple_emit_renders_command(tmp_path):
    # On the emit path (available=False) the write step renders a reproducible file-write command.
    steps = [{"write": ("sky.rad", "void glow g\n0\n")}]
    res = proc.run_sequence(steps, str(tmp_path), False, unavailable_reason="no rad")
    assert res["ran"] is False
    assert "sky.rad" in res["commands"][0]
    assert not (tmp_path / "sky.rad").exists()  # emit writes nothing
