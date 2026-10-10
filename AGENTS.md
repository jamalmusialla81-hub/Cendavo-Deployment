# Cendavo development instructions

Cendavo is an early SaaS product for laundromats, tailors, cleaning and repair businesses. Build one reusable product. Current increment: a five-page business website and a browser-local interactive workflow demo using synthetic data. No production customer data, payment, hosted accounts or outbound messaging exist.

Forge no longer invokes Codex; independent Claude reviewer sessions audit Builder code. If Codex is used manually, it audits Claude Builder's code and verifies test results. For any proposed feature, check security, user value, compatibility with Cloudflare Pages and whether the site accurately describes current capabilities. Do not infer that A$49–99/month is validated. Never commit secrets or deploy production without explicit user approval. Keep all overnight automation local, bounded, auditable and stoppable. Use `python3 scripts/build_site.py` and `python3 -m unittest discover -s tests` for checks.
