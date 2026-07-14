#!/usr/bin/env python
"""
ShopCheck UI-Model Exporter  (build_artifact)
=============================================

Renders the running ShopCheck app against its deterministic seed and extracts a
structured **UI model** — page objects, locators, and per-item element templates
— conforming to the frozen YAML schema owned by the QA generator repo
(`rag/ui_model.py`). Because ShopCheck owns its own source, this model is a
*build_artifact*: generated from the app, stamped with the repo's git SHA, and
regenerable on every change, so the model and the app cannot silently drift.

Locator policy (enforced, not advisory): the emitted `by:` field is a closed
enum — getByRole / getByLabel / getByPlaceholder / getByText / getByTitle /
getByAltText / getByTestId. CSS selectors, XPath, and raw `locator()` are never
emitted. An interactive element with no role/label/testid handle is *omitted and
logged as an instrumentation gap*, never selector-hacked (fail-closed).

Safety (this output is AGENT-FACING):
  * Runs only with DEFECT_MODE unset/0 and authenticates only as
    `standard_user`/`admin` — never `problem_user`. The model therefore reflects
    the clean UI (e.g. the handler-present logout button), and nothing about a
    planted imperfection is encoded.
  * A hard leak grep scans every emitted string before anything is written; on a
    hit the export aborts and writes NO output. This is the last gate before the
    content becomes agent-facing, so unlike the QA loader's warn-level tripwire
    it is a hard failure here.

Rendering uses FastAPI's in-process TestClient (deterministic, no port needed);
`base_url_key` is still emitted for the QA consumer's runtime. Self-validation is
an embedded copy of the frozen-schema checks (closed enum, required fields,
template closed-set resolution) so the exporter cannot emit something the QA
loader would reject; the cross-repo `kb_manager.py ui-model validate shopcheck`
remains the final manual acceptance check.

Usage:
    python tools/export_ui_model.py --out out/
    python tools/export_ui_model.py --dest <qa_repo>/kb/product_knowledge/ui_model/
    python tools/export_ui_model.py --out out/ --allow-dirty     # local iteration
"""
from __future__ import annotations

import argparse
import datetime as _dt
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

import yaml
from bs4 import BeautifulSoup

# Repo root = parent of tools/. Ensure `app` is importable when run as a script.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

APP_ID = "shopcheck"
DISPLAY_NAME = "ShopCheck"
ROUTES_FILE = Path(__file__).resolve().parent / "ui_model_routes.yaml"

# ── The closed `by:` enum (this IS the locator policy; CSS/XPath deliberately
# absent). Mirrors rag/ui_model.LOCATOR_METHODS in the QA repo. ────────────────
LOCATOR_METHODS: dict[str, dict[str, set]] = {
    "getByRole":        {"required": {"role"},  "optional": {"name", "exact"}},
    "getByLabel":       {"required": {"value"}, "optional": {"exact"}},
    "getByPlaceholder": {"required": {"value"}, "optional": set()},
    "getByText":        {"required": {"value"}, "optional": {"exact"}},
    "getByTitle":       {"required": {"value"}, "optional": set()},
    "getByAltText":     {"required": {"value"}, "optional": set()},
    "getByTestId":      {"required": {"value"}, "optional": set()},
}

SOURCE_TYPES = {"hand_curated", "dom_crawl", "build_artifact"}
SCHEMA_VERSION = 1

# ── Leak grep (HARD FAIL). Mirrors the APP_SPEC §16.4 / CLAUDE.md rule-1 mandate
# and the acceptance-criteria grep. `problem_user` is intentionally NOT here: it
# is a neutrally-named seed account (APP_SPEC §11) emitted only by name with a
# "test account" behavior — the forbidden thing is its *special behavior*, which
# this exporter never encodes. ───────────────────────────────────────────────
_LEAK_RE = re.compile(
    r"defect|DEFECT_MODE|ground.?truth|planted|deliberate|APP_SPEC|QA agent",
    re.IGNORECASE,
)

PROBLEM_USERNAME = "problem_user"  # the account we must never authenticate as

_TRAILING_ID_RE = re.compile(r"^(?P<base>.+)-(?P<id>\d+)$")
_PLACEHOLDER_RE = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


class ExportError(RuntimeError):
    """Raised on any guard failure or self-validation error. No output written."""


# ── Small helpers ──────────────────────────────────────────────────────────────

def leak_scan(text: str) -> list[str]:
    """Return the sorted set of forbidden terms found in `text` (case-insensitive)."""
    return sorted({m.group(0).lower() for m in _LEAK_RE.finditer(text or "")})


def slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return re.sub(r"-{2,}", "-", s)


def snake(token: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", token.lower()).strip("_")


def _collapse_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _looks_like_literal_url(val: Any) -> bool:
    return isinstance(val, str) and ("://" in val or val.startswith("/"))


# ── Seed-derived test data (the closed set for templated elements) ──────────────

def build_test_data() -> dict:
    """Derive test_data.yaml purely from the deterministic seed. Users are named
    neutrally; the closed product/order id sets back the element templates."""
    from app import seed

    users_out: dict[str, dict] = {}
    for _uid, username, _pw, _role, _locked in seed.USERS:
        users_out[username] = {
            "username_key": f"SHOPCHECK_{username.upper()}",
            "behavior": "test account",
        }

    products = [
        {"id": pid, "name": name, "slug": slugify(name)}
        for pid, name, _desc, _price, _stock, _active in seed.PRODUCTS
    ]
    orders = [{"id": oid, "status": status}
              for oid, _uid, status, _created, _items in seed.ORDERS]

    return {"users": users_out, "products": products, "orders": orders}


def _seed_id_sets() -> dict[str, set[int]]:
    from app import seed
    return {
        "product": {p[0] for p in seed.PRODUCTS},
        "order": {o[0] for o in seed.ORDERS},
    }


# ── HTML → element extraction ───────────────────────────────────────────────────

def _accessible_name(tag) -> str:
    aria = tag.get("aria-label")
    if aria:
        return _collapse_ws(aria)
    title = tag.get("title")
    if title and tag.name not in ("input", "select", "textarea"):
        return _collapse_ws(title)
    return _collapse_ws(tag.get_text())


def _label_text(tag, soup) -> Optional[str]:
    """Resolve a form control's accessible label: aria-label, or a <label for=id>."""
    aria = tag.get("aria-label")
    if aria:
        return _collapse_ws(aria)
    tid = tag.get("id")
    if tid:
        lab = soup.find("label", attrs={"for": tid})
        if lab:
            return _collapse_ws(lab.get_text())
    return None


def _implicit_role(tag) -> Optional[str]:
    explicit = tag.get("role")
    if explicit:
        return explicit
    if tag.name == "button":
        return "button"
    if tag.name == "a" and tag.get("href"):
        return "link"
    return None


def _build_locators(tag, soup) -> tuple[Optional[dict], Optional[dict]]:
    """Return (preferred, fallback) locator dicts per the getByRole-first policy,
    or (None, None) if the element has no addressable handle."""
    testid = tag.get("data-testid")
    testid_loc = {"by": "getByTestId", "value": testid} if testid else None

    # Form controls prefer getByLabel.
    if tag.name in ("input", "select", "textarea"):
        label = _label_text(tag, soup)
        placeholder = tag.get("placeholder")
        if label:
            return {"by": "getByLabel", "value": label}, testid_loc
        if placeholder:
            return {"by": "getByPlaceholder", "value": _collapse_ws(placeholder)}, testid_loc
        if testid_loc:
            return testid_loc, None
        return None, None

    role = _implicit_role(tag)
    if role:
        name = _accessible_name(tag)
        pref = {"by": "getByRole", "role": role}
        if name:
            pref["name"] = name
        return pref, testid_loc

    # Non-interactive but testid'd structural anchor (div/span/tr/table/pre).
    if testid_loc:
        return testid_loc, None
    return None, None


def _is_interactive(tag) -> bool:
    return tag.name in ("button", "a", "input", "select", "textarea")


def extract_page(html: str, *, scope: str, template_entity: Optional[str],
                 id_sets: dict[str, set[int]], conditional: set[str],
                 entities: dict) -> tuple[dict, dict, list[str]]:
    """Parse rendered HTML for one page.

    Returns (elements, element_templates, gaps). `elements`/`element_templates`
    are keyed dicts ready for YAML; `gaps` lists interactive elements that carry
    no addressable handle (instrumentation misses)."""
    soup = BeautifulSoup(html, "html.parser")
    root = soup.find(scope) or soup  # <header> or <main>; fall back to whole doc

    elements: dict[str, dict] = {}
    templates: dict[str, dict] = {}
    gaps: list[str] = []
    seen_testids: set[str] = set()

    closed_ids = id_sets.get(template_entity or "", set())

    # Only consider interactive tags, tags with a role, or tags with a testid.
    def _candidate(tag) -> bool:
        return bool(_is_interactive(tag) or tag.get("role") or tag.get("data-testid"))

    for tag in root.find_all(_candidate):
        testid = tag.get("data-testid")

        # ── Per-item template? testid = <base>-<seeded id in this page's set> ──
        if testid and template_entity:
            m = _TRAILING_ID_RE.match(testid)
            if m and int(m.group("id")) in closed_ids:
                base = m.group("base")
                tkey = snake(base)
                if tkey not in templates:
                    ent = entities[template_entity]
                    templates[tkey] = {
                        "param": ent["param"],
                        "param_source": ent["param_source"],
                        "preferred": {
                            "by": "getByTestId",
                            "value": f"{base}-{{{ent['param']}}}",
                        },
                        "conditional": False,
                    }
                continue  # do not also emit as an individual element

        if testid and testid in seen_testids:
            continue

        preferred, fallback = _build_locators(tag, soup)
        if preferred is None:
            if _is_interactive(tag):
                where = testid or tag.get("id") or _collapse_ws(tag.get_text())[:40]
                gaps.append(f"{tag.name}#{where}")
            continue

        # Element key: from testid, else from role+name.
        if testid:
            key = snake(testid)
            seen_testids.add(testid)
        else:
            role = preferred.get("role", "el")
            name = preferred.get("name", "")
            key = snake(f"{role}_{name}") if name else snake(role)
        if key in elements:
            continue

        entry: dict[str, Any] = {"preferred": preferred}
        if fallback:
            entry["fallback"] = fallback
        if testid in conditional:
            entry["conditional"] = True
        elements[key] = entry

    return elements, templates, gaps


# ── git provenance ──────────────────────────────────────────────────────────────

def _git(args: list[str]) -> Optional[str]:
    try:
        out = subprocess.run(["git", "-C", str(REPO_ROOT), *args],
                             capture_output=True, text=True)
    except FileNotFoundError:
        return None
    if out.returncode != 0:
        return None
    return out.stdout.strip()


def resolve_source_sha(allow_dirty: bool) -> str:
    """Return the short git SHA describing the rendered state. A build_artifact's
    trust rests on this describing exactly what was rendered."""
    sha = _git(["rev-parse", "--short", "HEAD"])
    if sha is None:
        if allow_dirty:
            return "nogit-dirty"
        raise ExportError(
            "not a git repository (or git unavailable) — a build_artifact needs a "
            "source_sha describing the rendered state. Initialize git and commit, "
            "or pass --allow-dirty for local iteration.")
    dirty = _git(["status", "--porcelain"])
    if dirty:
        if not allow_dirty:
            raise ExportError(
                "working tree is dirty — source_sha would not describe the rendered "
                "state. Commit your changes, or pass --allow-dirty to stamp "
                f"'{sha}-dirty' and continue.")
        return f"{sha}-dirty"
    return sha


# ── Model assembly ──────────────────────────────────────────────────────────────

def _login(client, role: str) -> None:
    """Authenticate a TestClient per a recipe role. Hard-refuses problem_user."""
    if role in (None, "anonymous"):
        return
    if role == PROBLEM_USERNAME:
        raise ExportError(
            "recipe requested authentication as 'problem_user' — refused. The model "
            "must reflect the clean UI; export as standard_user/admin only.")
    creds = {
        "admin": ("admin", "Admin123"),
        "standard_user": ("standard_user", "Secret123"),
    }
    if role not in creds:
        raise ExportError(f"unknown recipe auth role: {role!r}")
    username, password = creds[role]
    resp = client.post("/api/auth/login",
                       json={"username": username, "password": password})
    if resp.status_code != 200:
        raise ExportError(f"recipe login as {username} failed: {resp.status_code}")


def build_model(allow_dirty: bool) -> tuple[dict, dict, dict, dict, list[str]]:
    """Drive the app and return (manifest, pages, test_data, entities, gaps).

    pages: {page_object: page_dict}. Guards (DEFECT_MODE, git, problem_user) run
    here so a misconfigured run fails before any file is written."""
    # Guard: DEFECT_MODE must be off — the model is agent-facing and clean-only.
    if os.environ.get("DEFECT_MODE") == "1":
        raise ExportError(
            "DEFECT_MODE=1 is set — refusing to export. The UI model is "
            "agent-facing and must be generated from the clean state.")

    source_sha = resolve_source_sha(allow_dirty)

    routes = yaml.safe_load(ROUTES_FILE.read_text(encoding="utf-8"))
    base_url_key = routes["base_url_key"]
    entities = routes.get("entities", {})
    id_sets = _seed_id_sets()

    # Import the app lazily (after guards) and drive it in-process.
    from fastapi.testclient import TestClient
    from app import auth as app_auth
    from app.main import app

    pages: dict[str, dict] = {}
    all_gaps: list[str] = []

    with TestClient(app) as bootstrap:
        assert bootstrap.post("/api/reset").status_code == 200  # deterministic seed
        app_auth.clear_all_sessions()
        test_data = build_test_data()

        for spec in routes["pages"]:
            client = TestClient(app)
            _login(client, spec.get("recipe", {}).get("auth"))
            for step in spec.get("pre", []) or []:
                r = client.request(step["method"], step["path"],
                                   json=step.get("json"))
                exp = step.get("expect_status")
                if exp is not None and r.status_code != exp:
                    raise ExportError(
                        f"{spec['page_object']} pre-step {step['method']} "
                        f"{step['path']} expected {exp}, got {r.status_code}")
            resp = client.get(spec["route"])
            if resp.status_code != 200:
                raise ExportError(
                    f"{spec['page_object']} GET {spec['route']} returned "
                    f"{resp.status_code} (recipe/auth mismatch?)")

            elements, templates, gaps = extract_page(
                resp.text,
                scope=spec.get("scope", "main"),
                template_entity=spec.get("template_entity"),
                id_sets=id_sets,
                conditional=set(spec.get("conditional", []) or []),
                entities=entities,
            )
            all_gaps.extend(f"{spec['page_object']}: {g}" for g in gaps)

            page: dict[str, Any] = {
                "page_object": spec["page_object"],
                "url_path_key": spec["url_path_key"],
                "description": _collapse_ws(spec["description"]),
            }
            if spec.get("shared"):
                page["shared"] = True
            if elements:
                page["elements"] = elements
            if templates:
                page["element_templates"] = templates
            pages[spec["page_object"]] = page

    manifest = {
        "app_id": APP_ID,
        "display_name": DISPLAY_NAME,
        "source_type": "build_artifact",
        "base_url_key": base_url_key,
        "schema_version": SCHEMA_VERSION,
        "source_sha": source_sha,
        "generated_at": _dt.datetime.now().isoformat(timespec="seconds"),
    }
    return manifest, pages, test_data, entities, all_gaps


# ── Embedded self-validation (mirror of the frozen QA-repo schema checks) ────────

def _resolve_param_source(test_data: dict, path: str) -> Optional[list]:
    if not isinstance(path, str) or not path.strip():
        return None
    p = path.strip()
    if p.startswith("test_data."):
        p = p[len("test_data."):]
    if not p:
        return None
    values: list[Any] = [test_data]
    for tok in p.split("."):
        is_list = tok.endswith("[]")
        key = tok[:-2] if is_list else tok
        if not key:
            return None
        nxt: list[Any] = []
        for v in values:
            if not isinstance(v, dict) or key not in v:
                return None
            item = v[key]
            if is_list:
                if not isinstance(item, list):
                    return None
                nxt.extend(item)
            else:
                nxt.append(item)
        values = nxt
    if not values or any(not isinstance(v, (str, int, float, bool)) for v in values):
        return None
    return values


def _validate_locator(loc: Any, where: str, errors: list[str]) -> None:
    if not isinstance(loc, dict):
        errors.append(f"{where}: locator must be a mapping.")
        return
    by = loc.get("by")
    if by not in LOCATOR_METHODS:
        errors.append(f"{where}: '{by}' not in closed locator enum "
                      f"(CSS/XPath/raw selectors forbidden).")
        return
    for req in LOCATOR_METHODS[by]["required"]:
        if loc.get(req) in (None, ""):
            errors.append(f"{where}: '{by}' requires '{req}'.")


def validate_model(manifest: dict, pages: dict, test_data: dict) -> list[str]:
    """Run the frozen-schema checks in one pass; return the full error list."""
    errors: list[str] = []

    for req in ("app_id", "display_name", "source_type", "base_url_key", "schema_version"):
        if manifest.get(req) in (None, ""):
            errors.append(f"manifest: missing '{req}'.")
    if manifest.get("app_id") != APP_ID:
        errors.append(f"manifest: app_id must equal folder name '{APP_ID}'.")
    if manifest.get("source_type") not in SOURCE_TYPES:
        errors.append(f"manifest: bad source_type '{manifest.get('source_type')}'.")
    if manifest.get("source_type") == "build_artifact" and not manifest.get("source_sha"):
        errors.append("manifest: build_artifact requires 'source_sha'.")
    if manifest.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"manifest: unsupported schema_version {manifest.get('schema_version')}.")
    if _looks_like_literal_url(manifest.get("base_url_key")):
        errors.append("manifest: base_url_key must be an env key, not a literal URL.")

    seen_po: set[str] = set()
    for po, page in pages.items():
        for req in ("page_object", "url_path_key", "description"):
            if page.get(req) in (None, ""):
                errors.append(f"{po}: missing '{req}'.")
        if _looks_like_literal_url(page.get("url_path_key")):
            errors.append(f"{po}: url_path_key must be an env/config key, not a literal URL.")
        if page.get("page_object") in seen_po:
            errors.append(f"{po}: duplicate page_object.")
        seen_po.add(page.get("page_object"))

        elements = page.get("elements") or {}
        templates = page.get("element_templates") or {}
        if not elements and not templates:
            errors.append(f"{po}: page has neither elements nor element_templates.")

        for ekey, edef in elements.items():
            if edef.get("preferred") in (None, {}):
                errors.append(f"{po}::{ekey}: missing 'preferred'.")
            else:
                _validate_locator(edef["preferred"], f"{po}::{ekey}::preferred", errors)
            if edef.get("fallback") is not None:
                _validate_locator(edef["fallback"], f"{po}::{ekey}::fallback", errors)

        for tkey, tdef in templates.items():
            param = tdef.get("param")
            psrc = tdef.get("param_source")
            if param in (None, ""):
                errors.append(f"{po}::{tkey}: template missing 'param'.")
            if psrc in (None, ""):
                errors.append(f"{po}::{tkey}: template missing 'param_source'.")
            if tdef.get("preferred") in (None, {}):
                errors.append(f"{po}::{tkey}: missing 'preferred'.")
            else:
                _validate_locator(tdef["preferred"], f"{po}::{tkey}::preferred", errors)
            # Placeholder analysis + closed-set resolution.
            value_strings = [v for spec in (tdef.get("preferred"), tdef.get("fallback"))
                             if isinstance(spec, dict) for v in spec.values()
                             if isinstance(v, str)]
            placeholders: set[str] = set()
            for s in value_strings:
                placeholders.update(_PLACEHOLDER_RE.findall(s))
            if len(placeholders) > 1:
                errors.append(f"{po}::{tkey}: multiple placeholders {sorted(placeholders)} "
                              f"(one param per template).")
            if param and param not in placeholders:
                errors.append(f"{po}::{tkey}: '{{{param}}}' never appears in a value string.")
            if psrc and _resolve_param_source(test_data, psrc) is None:
                errors.append(f"{po}::{tkey}: param_source '{psrc}' does not resolve to a "
                              f"non-empty scalar list against test_data.")

    return errors


# ── Serialization + emit ────────────────────────────────────────────────────────

def _dump(data: dict) -> str:
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True, default_flow_style=False)


def _page_filename(page_object: str) -> str:
    name = re.sub(r"Page$", "", page_object)
    # Split camelCase boundaries so AdminDashboard -> admin_dashboard.
    name = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", name)
    return f"{snake(name)}_page.yaml"


def assemble_files(manifest: dict, pages: dict, test_data: dict) -> dict[str, str]:
    """Serialize the model to {relative_filename: yaml_text}. In-memory only —
    the leak grep runs over these strings BEFORE anything is written."""
    files = {"_manifest.yaml": _dump(manifest),
             "test_data.yaml": _dump(test_data)}
    for po, page in pages.items():
        files[_page_filename(po)] = _dump(page)
    return files


def run_leak_grep(files: dict[str, str]) -> None:
    """Hard fail if any emitted string contains a forbidden term."""
    hits: list[str] = []
    for name, text in files.items():
        found = leak_scan(text)
        if found:
            hits.append(f"{name}: {', '.join(found)}")
    if hits:
        raise ExportError(
            "LEAK GREP FAILED — forbidden term(s) in emitted output; wrote NOTHING:\n  - "
            + "\n  - ".join(hits))


def export(out_dir: Path, *, allow_dirty: bool = False,
           dest: Optional[Path] = None) -> dict:
    """Full pipeline: build → assemble → leak grep → self-validate → write → copy.
    Returns a summary dict. Raises ExportError before any write on guard/leak/
    validation failure."""
    manifest, pages, test_data, _entities, gaps = build_model(allow_dirty)
    files = assemble_files(manifest, pages, test_data)

    # 7. LEAK GREP (hard fail) — before any write.
    run_leak_grep(files)

    # 8. SELF-VALIDATE (embedded frozen-schema checks) — before any write.
    errors = validate_model(manifest, pages, test_data)
    if errors:
        raise ExportError("SELF-VALIDATION FAILED; wrote NOTHING:\n  - " + "\n  - ".join(errors))

    # 9. Write.
    app_dir = out_dir / "ui_model" / APP_ID
    app_dir.mkdir(parents=True, exist_ok=True)
    # Clear any stale page files from a previous export (shrink-and-rewrite).
    for old in app_dir.glob("*.yaml"):
        old.unlink()
    for name, text in files.items():
        (app_dir / name).write_text(text, encoding="utf-8")

    # 10. Optional cross-repo delivery.
    dest_dir = None
    if dest is not None:
        dest_dir = Path(dest) / APP_ID
        if dest_dir.exists():
            shutil.rmtree(dest_dir)
        shutil.copytree(app_dir, dest_dir)

    n_elements = sum(len(p.get("elements", {})) for p in pages.values())
    n_templates = sum(len(p.get("element_templates", {})) for p in pages.values())
    return {
        "app_dir": app_dir,
        "dest_dir": dest_dir,
        "pages": len(pages),
        "elements": n_elements,
        "templates": n_templates,
        "gaps": gaps,
        "source_sha": manifest["source_sha"],
        "products": len(test_data.get("products", [])),
    }


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Export the ShopCheck UI model (build_artifact).")
    ap.add_argument("--out", default="out", help="Output root (writes <out>/ui_model/shopcheck/).")
    ap.add_argument("--dest", default=None,
                    help="Also copy ui_model/shopcheck/ into this dir "
                         "(e.g. <qa_repo>/kb/product_knowledge/ui_model/).")
    ap.add_argument("--allow-dirty", action="store_true",
                    help="Permit a dirty/no-git tree; stamps source_sha with a -dirty suffix.")
    args = ap.parse_args(argv)

    try:
        summary = export(Path(args.out), allow_dirty=args.allow_dirty,
                         dest=Path(args.dest) if args.dest else None)
    except ExportError as e:
        print(f"❌ export aborted: {e}", file=sys.stderr)
        return 1

    print(f"✅ UI model exported to {summary['app_dir']}")
    print(f"   source_sha={summary['source_sha']}  pages={summary['pages']}  "
          f"elements={summary['elements']}  templates={summary['templates']}  "
          f"products={summary['products']}")
    if summary["dest_dir"]:
        print(f"   copied to {summary['dest_dir']}")
    if summary["gaps"]:
        print(f"   ⚠ {len(summary['gaps'])} instrumentation gap(s) — "
              f"interactive elements with no stable locator:")
        for g in summary["gaps"]:
            print(f"       - {g}")
    else:
        print("   no instrumentation gaps.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
