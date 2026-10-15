"""Regenerate docs/SOURCE_MATRIX.md from the seed catalogue (python scripts/generate_source_matrix.py)."""
from pathlib import Path

from app.data.sources import SEED_SOURCES

STATUS = {"active": "✅ active", "pending_credentials": "🔑 needs API key", "pending_license": "📄 needs licence + adapter",
          "manual": "✎ manual queue", "catalog_only": "📚 catalogue only"}


def main() -> None:
    lines = ["# Source inventory & integration suitability matrix", "",
             "_Generated from `backend/app/data/sources.py`. Licence/ToS notes are operator summaries and must be re-verified before production use._", "",
             "| Tier | Source | Purpose | Countries | Access model | Status in this build | Auth | Export | Retention | Notes |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for s in sorted(SEED_SOURCES, key=lambda x: (x["tier"], x["integration_status"] != "active", x["name"])):
        countries = "global" if "*" in s["countries"] else ", ".join(s["countries"])
        if len(countries) > 40:
            countries = countries[:37] + "…"
        note = (s.get("terms_summary") or s.get("notes") or "").replace("|", "/")
        lines.append(f"| {s['tier']} | {s['name']} | {', '.join(s['purposes'])} | {countries} | {s['access_model']} | "
                     f"{STATUS.get(s['integration_status'], s['integration_status'])} | {s.get('auth_required') or '–'} | "
                     f"{'yes' if s['export_allowed'] else 'no'} | {str(s['max_retention_days']) + ' d' if s['max_retention_days'] else '–'} | {note[:220]} |")
    Path(__file__).resolve().parents[2].joinpath("docs/SOURCE_MATRIX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
