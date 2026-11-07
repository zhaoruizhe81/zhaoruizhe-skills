# Quality Checklist

Before delivering a notebook:

- Run it top-to-bottom at least once (or as much as the environment allows).
- Ensure early cells set all required state; avoid hidden state from prior runs.
- Keep outputs tidy. Avoid giant outputs when a short summary works.
- Prefer small tables, key metrics, or short printouts.
- Keep the narrative skimmable. Use headings and short bullets, and avoid long paragraphs.
- Leave helpful TODOs only when necessary, and label them clearly.
- If execution is not possible, call out the risk and how to validate locally.
- If plots contain non-ASCII text (e.g. Chinese), confirm the glyphs render (not boxes/□). With seaborn, the CJK font must be set via `sns.set_style(..., {"font.sans-serif": [...]})` — see SKILL.md "Chinese text in plots". Verify by OCR (`pytesseract`, `chi_sim`), not by eye or vision tools.
