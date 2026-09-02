"""UTF-8 text I/O with a fixed newline policy for generated Radiance inputs.

read_text: universal newlines (CRLF -> LF on read). write_text: LF only (no CR), so files fed
to Radiance parsers (.pts, .wea) are byte-identical across OSes and never carry a Windows CR."""


def read_text(path):
    """Read a text file as UTF-8 with universal newline translation."""
    with open(path, "r", encoding="utf-8", newline=None) as fh:
        return fh.read()


def write_text(path, text, *, append=False):
    """Write text as UTF-8 with LF line endings. Any CR in the source is normalized to LF, so the
    output is unconditionally LF-only. append=True opens in append mode."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    with open(path, "a" if append else "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
