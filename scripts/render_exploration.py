#!/usr/bin/env python3
"""Regenerate public diagrams using the installed diagram skills.

Only HEAD's tracked files enter the scan. Private files, symlinks, and the
generated exploration tree are excluded before any file content is read.
"""

import argparse
import importlib.util
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import xml.etree.ElementTree as ET
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = {"foundation.md", "provenance.md", ".voice", "voice-corpus"}

WORKFLOW = {
    "mode": "flow", "darkTheme": "midnight", "lightTheme": "daylight",
    "defaultMode": "auto", "title": "Checked CV export",
    "titleHighlight": "Local workflow",
    "subtitle": "Follow approved wording through one shared export and validation path.",
    "footer": "Candidate approval precedes rendering. Visual and factual review remain required; export checks do not certify ATS parsing.",
    "nodes": [
        {"id": "approved", "label": "Approved wording", "shape": "pill"},
        {"id": "structured", "label": "Structured JSON", "sublabel": "Repeatable input"},
        {"id": "manual", "label": "Approved HTML", "sublabel": "Legacy option"},
        {"id": "build", "label": "Shared print layout", "sublabel": "Lane + A4 / Letter"},
        {"id": "posting", "label": "Optional posting", "shape": "pill"},
        {"id": "render", "label": "Temporary PDF", "sublabel": "Fresh browser profile"},
        {"id": "checks", "label": "Delivery checks", "sublabel": "PDF text + posting"},
        {"id": "pass", "label": "Checks pass?", "shape": "decision"},
        {"id": "preserve", "label": "Keep prior output", "shape": "pill"},
        {"id": "publish", "label": "Checked PDF", "sublabel": "Atomic publication"},
        {"id": "review", "label": "Visual/fact review", "shape": "pill"},
    ],
    "edges": [
        {"from": "approved", "to": "structured", "kind": "main"},
        {"from": "approved", "to": "manual", "kind": "sync"},
        {"from": "structured", "to": "build", "kind": "main"},
        {"from": "build", "to": "render", "kind": "main"},
        {"from": "manual", "to": "render", "kind": "sync"},
        {"from": "render", "to": "checks", "kind": "main"},
        {"from": "posting", "to": "checks", "kind": "async"},
        {"from": "checks", "to": "pass", "kind": "main"},
        {"from": "pass", "to": "preserve", "kind": "sync", "label": "no"},
        {"from": "pass", "to": "publish", "kind": "main", "label": "yes"},
        {"from": "publish", "to": "review", "kind": "main"},
    ],
    "journeys": [
        {"hops": [["structured", "build"], ["build", "render"], ["render", "checks"]]},
        {"hops": [["pass", "publish"], ["publish", "review"]]},
    ],
}

WORKFLOW_STYLE = """
<style id="project-presentation">
body { padding:24px; }
.header { align-items:flex-start; }
h1 { line-height:1.45; }
.subtitle { color:var(--legend-text); font-size:.9rem; line-height:1.6; }
.footer { color:var(--legend-text); font-size:.8rem; line-height:1.7; }
.ctrls { position:static; justify-content:flex-end; margin-bottom:16px; }
.ctrl { min-height:44px; color:var(--text); }
.diagram-card { overflow-x:auto; }
#flowsvg { display:block; max-width:100%; }
:root { --subtext:#9cacc4; }
:root[data-theme="light"] { --subtext:#475569; }
button:focus-visible,a:focus-visible { outline:3px solid var(--pulse); outline-offset:4px; }
.map-nav { margin:0 0 18px; font-size:.9rem; }
.map-nav a { color:var(--text); }
.mobile-hint { display:none; }
@media(max-width:600px) {
  body { padding:16px; }
  .header { gap:8px; }
  h1 { font-size:1.1rem; }
  .capsule { font-size:.8rem; margin-left:4px; }
  .diagram-card { padding:12px; }
  #flowsvg { min-width:560px; max-width:none; }
  .mobile-hint { display:block; color:var(--legend-text); font-size:.8rem; margin-bottom:12px; line-height:1.6; }
}
</style>
"""

MAP_STYLE = """
<style id="project-presentation">
button:focus-visible,a:focus-visible,select:focus-visible { outline:3px solid var(--accent); outline-offset:3px; }
#search { min-width:0; }
#top h1 { letter-spacing:.04em; text-indent:0; }
#top h1 small { letter-spacing:.06em; }
#railToggle { display:none; }
.map-home { color:var(--fg); font-size:12px; padding:8px; }
@media(max-width:700px) {
  #top { gap:5px; padding:8px; }
  #top h1 { width:100%; margin:0; white-space:normal; }
  #sub,#top .sep,#help,#ovLegend,#mStar { display:none!important; }
  #search { flex-basis:100%; padding:10px; font-size:13px; }
  #modes { margin-right:auto; }
  #modes button { min-height:44px; padding:5px 10px; letter-spacing:0; }
  #top>button { min-height:44px; padding:6px 10px; letter-spacing:0; }
  #view,#bImports,#bCalls,#bExt,#bHier,#bFold,#bHood,#bEntry,#bCycles,#bFit { display:none!important; }
  #railToggle { display:block; }
  #rail { display:none!important; top:var(--map-top,190px); width:calc(100% - 24px); max-height:calc(100dvh - var(--map-top,190px) - 24px); }
  body.files-open #rail { display:block!important; }
  body.files-open #rail:has(#hitsWrap[style*="block"]) #startHere,
  body.files-open #rail:has(#hitsWrap[style*="block"]) #stats { display:none; }
  #hitsWrap { order:-1; }
  #rail { flex-direction:column; }
  body.files-open #rail { display:flex!important; }
  #info { left:12px; right:12px; top:auto; bottom:12px; width:auto; max-height:44dvh; }
  #tour { padding:12px; max-height:38dvh; overflow:auto; }
  #tour .hd { flex-wrap:wrap; gap:7px; }
  #tour .ti { letter-spacing:.03em; font-size:12px; }
  #tour .note { font-size:13px; line-height:1.6; letter-spacing:0; }
  #tour .hd button { min-width:44px; min-height:44px; }
  body:has(#tour.show) #info { display:none; }
  #ov,#sky { top:var(--map-top,190px); }
  #ovScroll { justify-content:flex-start; padding:24px 12px; }
  #tip { max-width:calc(100vw - 24px); }
}
</style>
"""

MAP_BINDINGS = """
const filesButton = document.getElementById("railToggle");
filesButton.onclick = () => {
  const open = document.body.classList.toggle("files-open");
  filesButton.setAttribute("aria-expanded", String(open));
};
document.getElementById("search").addEventListener("input", () => {
  setMode("explore");
  if (innerWidth <= 700) {
    document.body.classList.add("files-open");
    filesButton.setAttribute("aria-expanded", "true");
  }
});
const topBar = document.getElementById("top");
const updateMapTop = () => document.documentElement.style.setProperty("--map-top", `${Math.ceil(topBar.getBoundingClientRect().bottom + 12)}px`);
new ResizeObserver(updateMapTop).observe(topBar);
updateMapTop();
document.getElementById("bMotion").setAttribute("aria-label", "Pause or resume map motion");
document.getElementById("bTheme").setAttribute("aria-label", "Switch map theme");
document.getElementById("search").setAttribute("aria-label", "Search public files and symbols");
document.querySelectorAll("[data-entry],[data-layer]").forEach(element => {
  element.tabIndex = 0;
  element.setAttribute("role", "button");
  element.addEventListener("keydown", event => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault(); event.stopPropagation(); element.click();
    }
  });
});
const hits = document.getElementById("hits");
new MutationObserver(() => {
  hits.querySelectorAll("[data-id]").forEach(element => {
    element.tabIndex = 0;
    element.setAttribute("role", "button");
  });
}).observe(hits, { childList:true });
hits.addEventListener("keydown", event => {
  const target = event.target.closest("[data-id]");
  if (target && (event.key === "Enter" || event.key === " ")) {
    event.preventDefault(); event.stopPropagation(); target.click();
  }
});
document.getElementById("rail").addEventListener("click", event => {
  if (innerWidth <= 700 && event.target.closest("[data-id],[data-entry]")) {
    document.body.classList.remove("files-open");
    filesButton.setAttribute("aria-expanded", "false");
  }
});
"""

def replace_once(source, old, new):
    if source.count(old) != 1:
        raise ValueError("Diagram generator presentation changed; review the adaptation before regeneration.")
    return source.replace(old, new, 1)


def embedded_icon():
    logo = (ROOT / "assets/mark.svg").read_text(encoding="utf-8")
    return '<link rel="icon" href="data:image/svg+xml,' + quote(logo, safe="") + '" type="image/svg+xml">'


def adapt_workflow(source):
    source = replace_once(source, "</head>", embedded_icon() + "\n" + WORKFLOW_STYLE + "\n</head>")
    source = replace_once(source, '<div class="container">', '<div class="container">\n<nav class="map-nav"><a href="index.html">Back to project exploration</a></nav>')
    source = replace_once(source, '  <div class="diagram-card">', '  <p class="mobile-hint">Scroll the diagram sideways for readable labels. The full workflow and source guide are also linked from the exploration page.</p>\n  <div class="diagram-card" tabindex="0" aria-label="Scrollable export workflow">')
    return source


def adapt_source_map(source):
    source = replace_once(source, "</head>", embedded_icon() + "\n" + MAP_STYLE + "\n</head>")
    source = replace_once(source, '<div class="panel" id="top">', '<div class="panel" id="top">\n  <a class="map-home" href="index.html">Project guide</a>\n  <button id="railToggle" type="button" aria-controls="rail" aria-expanded="false">Files</button>')
    source = replace_once(source, 'const ovWorthShowing = OV && OV.boxes.length >= 2;', 'const ovWorthShowing = OV && OV.boxes.length >= 2 && OV.edges.length > 0;')
    source = replace_once(source, '  S.tx = 268;\n  S.ty = 96;', '  S.tx = innerWidth <= 700 ? 28 : 268;\n  S.ty = innerWidth <= 700 ? document.getElementById("top").getBoundingClientRect().bottom + 32 : 96;')
    source = replace_once(source, '  sc = Math.max(0.28, Math.min(1, sc));', '  sc = Math.max(innerWidth <= 700 ? .72 : .28, Math.min(1, sc));')
    source = replace_once(source, '  S.mode = m;', '  S.mode = m;\n  document.body.classList.remove("files-open");\n  const drawer = document.getElementById("railToggle");\n  if (drawer) drawer.setAttribute("aria-expanded", "false");\n  for (const [id, mode] of [["mOverview","overview"],["mStar","star"],["mExplore","explore"]]) document.getElementById(id).setAttribute("aria-selected", String(m === mode));')
    source = replace_once(source, '  if (ev.key === "Tab") {', '  if (ev.key.toLowerCase() === "v" && !ev.ctrlKey && !ev.metaKey && !ev.altKey) {')
    source = source.replace("Tab overview / explore", "V views · Tab focus")
    source = replace_once(source, 'setMotion(!REDUCED);\nrequestAnimationFrame(frame);', 'setMotion(!REDUCED);\n' + MAP_BINDINGS + "\nrequestAnimationFrame(frame);")
    return source


def public_snapshot(root, destination, revision="HEAD"):
    """Validate tree metadata before asking Git for any tracked file contents."""
    tree = subprocess.run(["git", "-C", str(root), "ls-tree", "-r", "-z", revision],
                          check=True, capture_output=True).stdout
    approved = []
    for record in tree.split(b"\0"):
        if not record:
            continue
        metadata, filename = record.split(b"\t", 1)
        mode, kind, _ = metadata.decode("ascii").split()
        name = filename.decode("utf-8")
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("Unsafe tracked snapshot path.")
        if any(part.casefold() in PRIVATE for part in path.parts):
            raise ValueError("Private sources must never be tracked in the public snapshot.")
        if mode not in {"100644", "100755"} or kind != "blob":
            raise ValueError("Tracked symlinks and submodules are not accepted in a public diagram snapshot.")
        if path.parts[:2] != ("assets", "explore"):
            approved.append(name)
    if not approved:
        raise ValueError("No public tracked sources selected.")
    archive = subprocess.run(["git", "-C", str(root), "archive", revision, "--", *approved],
                             check=True, capture_output=True,
                             env={**os.environ, "GIT_LITERAL_PATHSPECS": "1"}).stdout
    destination.mkdir(mode=0o700, parents=True)
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as content:
        for member in content:
            if member.isdir():
                continue
            if member.name not in approved or not member.isfile():
                raise ValueError("Archive differs from the approved public tree.")
            target = destination.joinpath(*PurePosixPath(member.name).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content.extractfile(member).read())


def validate_output_directory(output):
    if any(path.is_symlink() for path in (output,) + tuple(output.parents)):
        raise ValueError("Diagram output must not follow symlinked directories.")


def publish_artifacts(staged, output):
    """Publish only a complete validated set; roll back ordinary I/O failures."""
    names = ("codegraph.html", "workflow.html", "workflow-preview.svg")
    if any(not (staged / name).is_file() or not (staged / name).stat().st_size for name in names):
        raise ValueError("The validated diagram set is incomplete.")
    validate_output_directory(output)
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".explore-publish-", dir=output) as temporary:
        temporary = Path(temporary)
        existed = set()
        for name in names:
            target = output / name
            if target.exists():
                if target.is_symlink() or not target.is_file() or target.stat().st_nlink != 1:
                    raise ValueError("Diagram destination must be an ordinary file.")
                shutil.copyfile(target, temporary / (name + ".previous"))
                existed.add(name)
            shutil.copyfile(staged / name, temporary / (name + ".next"))
        published = []
        try:
            for name in names:
                os.replace(temporary / (name + ".next"), output / name)
                published.append(name)
        except OSError:
            for name in reversed(published):
                if name in existed:
                    os.replace(temporary / (name + ".previous"), output / name)
                else:
                    (output / name).unlink()
            raise


def public_metadata(graph, revision):
    """Redact build location; preserve every scanner-produced node and edge."""
    graph["project"].pop("root", None)
    graph["project"]["name"] = "cv-witness"
    graph["project"]["gitCommitHash"] = revision
    return graph


def workflow_preview(source):
    """Preserve generated geometry in an opaque, fixed-light README image."""
    svg = ET.fromstring(re.search(r'(<svg id="flowsvg".*?</svg>)', source, flags=re.DOTALL)[1])
    palette_source = re.search(r':root\[data-theme="light"\]\s*\{([^}]+)\}', source)[1]
    palette = dict(re.findall(r"--([\w-]+)\s*:\s*([^;]+)", palette_source))
    palette = {key: value.strip() for key, value in palette.items()}
    palette.update({
        "text": "#0f172a", "subtext": "#475569",
        "flow-node-fill": "#ffffff", "flow-pill-fill": "#e6f4ef",
        "flow-node-stroke": "#047857", "flow-pill-stroke": "#047857",
        "flow-conn": "#047857",
    })
    tag = lambda element: element.tag.rsplit("}", 1)[-1]
    for parent in svg.iter():
        for child in list(parent):
            if tag(child) in {"style", "script", "animate", "animateMotion", "filter"} or set(child.get("class", "").split()) & {"dot", "trail", "halo"}:
                parent.remove(child)
    font = "ui-monospace, Menlo, Consolas, monospace"
    for element in svg.iter():
        for declaration in element.attrib.pop("style", "").split(";"):
            if ":" not in declaration:
                continue
            key, value = declaration.split(":", 1)
            element.set(key.strip(), value.strip())
        for key, value in list(element.attrib.items()):
            value = re.sub(r"var\(--([\w-]+)\)", lambda match: palette[match[1]], value)
            element.set(key, value.replace("context-stroke", "#047857"))
        element.attrib.pop("filter", None)
        if "font-family" in element.attrib or tag(element) == "text":
            element.set("font-family", font)
        if element.get("class") == "flow-async":
            element.set("stroke-dasharray", "3 4")
        if element.get("id") == "flowsvg-title":
            element.text = "Checked CV export workflow"
        elif element.get("id") == "flowsvg-desc":
            element.text = "Approved wording enters the shared layout and delivery checks. Failure preserves prior output; checked output still needs visual and factual review."
    x, y, width, height = map(float, svg.get("viewBox").split())
    svg.set("xmlns", "http://www.w3.org/2000/svg")
    svg.set("width", "600")
    svg.set("height", str(round(600 * height / width)))
    svg.set("font-family", font)
    background = ET.Element("rect", {
        "id": "preview-background", "x": f"{x:g}", "y": f"{y:g}",
        "width": f"{width:g}", "height": f"{height:g}", "rx": "12",
        "fill": "#f8fafc",
    })
    svg.insert(0, background)
    return ET.tostring(svg, encoding="unicode") + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codegraph-skill", type=Path)
    parser.add_argument("--glowmotion-skill", type=Path)
    parser.add_argument("--preview-only", action="store_true",
                        help="Refresh the fixed-light README image from the existing checked workflow")
    args = parser.parse_args(argv)
    if args.preview_only:
        output = ROOT / "assets/explore"
        validate_output_directory(output)
        preview = workflow_preview((output / "workflow.html").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory(prefix=".workflow-preview-", dir=output) as temporary:
            staged = Path(temporary) / "workflow-preview.svg"
            staged.write_text(preview, encoding="utf-8")
            os.replace(staged, output / "workflow-preview.svg")
        print("Updated the fixed-light README workflow preview.")
        return
    if args.codegraph_skill is None or args.glowmotion_skill is None:
        parser.error("Full regeneration needs --codegraph-skill and --glowmotion-skill.")
    codegraph = args.codegraph_skill.expanduser().resolve()
    glowmotion = args.glowmotion_skill.expanduser().resolve()
    output = ROOT / "assets" / "explore"
    revision = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
    with tempfile.TemporaryDirectory(prefix="cv-witness-public-map-") as temporary:
        temporary = Path(temporary).resolve()
        snapshot = temporary / "cv-witness"
        public_snapshot(ROOT, snapshot, revision)
        staged = temporary / "artifacts"
        staged.mkdir()
        scan_dir = temporary / "scan"
        subprocess.run([sys.executable, str(codegraph / "scripts/scan.py"), str(snapshot), "--no-calls", "-o", str(scan_dir)], check=True)
        graph = json.loads((scan_dir / "graph.json").read_text())
        enrichment = json.loads((ROOT / "docs/exploration-enrichment.json").read_text())
        sys.path.insert(0, str(codegraph / "scripts"))
        spec = importlib.util.spec_from_file_location("codegraph_renderer", codegraph / "scripts/render.py")
        renderer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(renderer)
        errors, warnings = renderer.validate_graph(graph)
        clean, enrichment_warnings = renderer.validate_enrich(enrichment, {node["id"] for node in graph["nodes"]})
        if errors or warnings or enrichment_warnings:
            raise ValueError("Source-map validation failed: " + "; ".join(errors + warnings + enrichment_warnings))
        graph = public_metadata(renderer.merge(graph, clean), revision)
        result = "\n".join(line.rstrip() for line in adapt_source_map(renderer.render_html(graph, "cv-witness")).splitlines()) + "\n"
        if "/Users/" in result or "/Volumes/" in result:
            raise ValueError("Local build metadata remains in the public source map.")
        renderer.deliver(result, str(staged / "codegraph.html"))
        graph_input = temporary / "workflow.json"
        graph_input.write_text(json.dumps(WORKFLOW), encoding="utf-8")
        subprocess.run([sys.executable, str(glowmotion / "scripts/layout.py"), str(graph_input), "--render", str(staged / "workflow.html")], check=True)
        workflow = "\n".join(line.rstrip() for line in adapt_workflow((staged / "workflow.html").read_text()).splitlines()) + "\n"
        (staged / "workflow.html").write_text(workflow, encoding="utf-8")
        subprocess.run([sys.executable, str(glowmotion / "scripts/check_diagram.py"), str(staged / "workflow.html")], check=True)
        (staged / "workflow-preview.svg").write_text(workflow_preview(workflow), encoding="utf-8")
        publish_artifacts(staged, output)
        print(json.dumps({"revision": revision, "nodes": len(graph["nodes"]), "edges": len(graph["edges"]),
                          "summaries": graph.get("enrichedNodes"), "tours": len(graph.get("tour", [])),
                          "private_sources_scanned": False}))


if __name__ == "__main__":
    main()
