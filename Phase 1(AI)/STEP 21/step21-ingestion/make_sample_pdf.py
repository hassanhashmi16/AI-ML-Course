"""Generate a two-column sample PDF with no external dependencies.

The content stream emits glyphs in reading-scrambled order (left headline,
right headline, left body, right body) so naive extraction visibly fails,
while a layout-aware parser recovers the correct order. Run: python make_sample_pdf.py
"""


def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _content_stream(lines: list[tuple[float, float, str, int]]) -> str:
    parts = []
    for x, y, text, size in lines:
        parts.append(f"BT /F1 {size} Tf {x} {y} Td ({_esc(text)}) Tj ET")
    return "\n".join(parts)


def _build_pdf() -> bytes:
    # Two columns: left at x=50, right at x=320. y runs top-to-bottom.
    lines = [
        # Page title (full width, correct reading position first)
        (50, 720, "Quarterly Business Review", 16),

        # Scrambled on purpose: left headline, then right headline, then bodies.
        (50, 680, "Revenue grew 12% in Q3", 13),
        (320, 680, "Attrition fell to 8%", 13),

        (50, 655, "Driven by the enterprise segment", 11),
        (50, 640, "which expanded into two new regions.", 11),
        (320, 655, "as retention programs matured and", 11),
        (320, 640, "onboarding improved across teams.", 11),

        # A simple table rendered as positioned text.
        (50, 600, "Name  Age  Region", 11),
        (50, 585, "Alice 30   EMEA", 11),
        (50, 570, "Bob   25   APAC", 11),
    ]

    content = _content_stream(lines)

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>"
        ),
        b"<< /Length " + str(len(content.encode("latin-1"))).encode() + b" >>\nstream\n"
        + content.encode("latin-1")
        + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]

    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode()
        out += obj + b"\nendobj\n"

    xref_pos = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for off in offsets[1:]:
        out += f"{off:010d} 00000 n \n".encode()

    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_pos}\n%%EOF\n"
    ).encode()
    return bytes(out)


if __name__ == "__main__":
    path = "sample_report.pdf"
    with open(path, "wb") as f:
        f.write(_build_pdf())
    print(f"wrote {path}")
