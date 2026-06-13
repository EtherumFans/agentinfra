"""Evidence-linked report rendering (PHI-safe).

Renders the de-identified text (run.redaction['text']) with each code's evidence spans
highlighted, plus codes / candidates / compliance gate / DRG route / version footer.
Never renders raw PHI — it only ever sees the redacted text.
"""
