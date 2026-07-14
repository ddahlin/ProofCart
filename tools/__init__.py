"""ShopCheck build/eval tooling (not agent-facing).

Only the *output* of tools/export_ui_model.py (the emitted YAML under
out/ui_model/) is agent-facing and subject to the CLAUDE.md rule 1 / APP_SPEC
§16.4 leak grep. The tools themselves live in the build layer alongside
APP_SPEC.md.
"""
