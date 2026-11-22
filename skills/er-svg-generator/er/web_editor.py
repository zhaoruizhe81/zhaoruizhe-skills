from __future__ import annotations

import argparse
import json
import math
import sys
import webbrowser
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .export import POSITION_PRECISION, export_layout
from .layout import build_layout
from .model import ERError, Layout, VALID_POST_LAYOUTS
from .parser import apply_layout_file, load_spec
from .png_export import export_png
from .post_layout import apply_post_layout
from .render_svg import escape_id, render_svg
from .stats import route_stats



@dataclass(frozen=True)
class WebEditorConfig:
    input_path: Path
    output_path: Path
    layout_path: Path
    png_path: Path | None
    host: str
    port: int
    open_browser: bool
    post_layout: str | None
    debug_territory: bool
    target_aspect: float | None
    png_scale: float
    png_dpi: int
    png_width: int | None


class WebEditor:
    def __init__(self, config: WebEditorConfig) -> None:
        self.config = config

    def state(self, write_outputs: bool = False) -> dict[str, Any]:
        use_layout_file = self.config.layout_path.exists()
        result = self.render(use_layout_file=use_layout_file, write_outputs=write_outputs)
        if write_outputs and not use_layout_file:
            export_layout(result["layout"], self.config.layout_path)
            result = self.render(use_layout_file=True, write_outputs=True)
        return result

    def preview(self, payload: dict[str, Any]) -> dict[str, Any]:
        positions = self.clean_positions(payload.get("positions", {}))
        return self.render(positions=positions, post_layout="none", debug_territory=self.payload_debug(payload))

    def save(self, payload: dict[str, Any]) -> dict[str, Any]:
        positions = self.clean_positions(payload.get("positions", {}))
        result = self.render(
            positions=positions,
            post_layout="none",
            write_outputs=True,
            debug_territory=self.payload_debug(payload),
        )
        export_layout(result["layout"], self.config.layout_path)
        result["saved"] = True
        return result

    def reset(self) -> dict[str, Any]:
        if self.config.layout_path.exists():
            self.config.layout_path.unlink()
        result = self.render(use_layout_file=False, write_outputs=True)
        export_layout(result["layout"], self.config.layout_path)
        result["reset"] = True
        return result

    def render(
        self,
        positions: dict[str, dict[str, dict[str, float]]] | None = None,
        use_layout_file: bool = False,
        post_layout: str | None = None,
        write_outputs: bool = False,
        debug_territory: bool | None = None,
    ) -> dict[str, Any]:
        spec = load_spec(self.config.input_path)
        if self.config.target_aspect is not None:
            spec.layout.target_aspect = self.config.target_aspect
        if positions is not None:
            spec.layout.entity_positions.update(position_tuples(positions.get("entities", {})))
            spec.layout.relationship_positions.update(position_tuples(positions.get("relationships", {})))
        elif use_layout_file:
            apply_layout_file(spec, self.config.layout_path)

        layout = build_layout(spec)
        mode = post_layout
        if mode is None:
            mode = "none" if positions is not None or use_layout_file else self.config.post_layout or spec.layout.post_layout
        apply_post_layout(layout, mode)
        layout.debug_territory = (
            debug_territory if debug_territory is not None else self.config.debug_territory or spec.layout.territory_debug
        )
        svg = render_svg(layout, spec.title)
        stats = route_stats(layout)
        png_error = None

        if write_outputs:
            self.config.output_path.parent.mkdir(parents=True, exist_ok=True)
            self.config.output_path.write_text(svg, encoding="utf-8")
            if self.config.png_path is not None:
                try:
                    export_png(
                        self.config.output_path,
                        self.config.png_path,
                        scale=self.config.png_scale,
                        dpi=self.config.png_dpi,
                        width=self.config.png_width,
                    )
                except ERError as exc:
                    png_error = str(exc)

        return {
            "svg": svg,
            "stats": stats,
            "positions": layout_positions(layout),
            "nodes": editable_nodes(layout),
            "paths": {
                "input": str(self.config.input_path),
                "output": str(self.config.output_path),
                "layout": str(self.config.layout_path),
                "png": str(self.config.png_path) if self.config.png_path is not None else None,
            },
            "postLayout": mode,
            "debugTerritory": layout.debug_territory,
            "pngError": png_error,
            "layout": layout,
        }

    def payload_debug(self, payload: dict[str, Any]) -> bool | None:
        value = payload.get("debugTerritory")
        if value is None:
            return None
        if not isinstance(value, bool):
            raise ERError("debugTerritory must be a boolean")
        return value

    def clean_positions(self, raw: Any) -> dict[str, dict[str, dict[str, float]]]:
        if not isinstance(raw, dict):
            raise ERError("positions must be an object")
        spec = load_spec(self.config.input_path)
        relationship_ids = {relationship.id for relationship in spec.relationships}
        result: dict[str, dict[str, dict[str, float]]] = {"entities": {}, "relationships": {}}
        for group, valid_ids in (("entities", set(spec.entities)), ("relationships", relationship_ids)):
            raw_group = raw.get(group, {}) or {}
            if not isinstance(raw_group, dict):
                raise ERError(f"positions.{group} must be an object")
            for item_id, value in raw_group.items():
                if item_id not in valid_ids:
                    raise ERError(f"positions.{group} references unknown id: {item_id}")
                if not isinstance(value, dict):
                    raise ERError(f"positions.{group}.{item_id} must be an object")
                x = value.get("x")
                y = value.get("y")
                if not isinstance(x, int | float) or not isinstance(y, int | float):
                    raise ERError(f"positions.{group}.{item_id} must contain numeric x and y")
                if not math.isfinite(float(x)) or not math.isfinite(float(y)):
                    raise ERError(f"positions.{group}.{item_id} coordinates must be finite")
                result[group][item_id] = {
                    "x": round(float(x), POSITION_PRECISION),
                    "y": round(float(y), POSITION_PRECISION),
                }
        return result


def position_tuples(raw: dict[str, dict[str, float]]) -> dict[str, tuple[float, float]]:
    return {item_id: (float(value["x"]), float(value["y"])) for item_id, value in raw.items()}


def layout_positions(layout: Layout) -> dict[str, dict[str, dict[str, float]]]:
    positions: dict[str, dict[str, dict[str, float]]] = {"entities": {}, "relationships": {}}
    for node in layout.nodes.values():
        if node.kind == "entity":
            positions["entities"][node.id] = {
                "x": round(node.x, POSITION_PRECISION),
                "y": round(node.y, POSITION_PRECISION),
            }
        elif node.kind == "relationship" and node.id.startswith("rel:"):
            positions["relationships"][node.id.removeprefix("rel:")] = {
                "x": round(node.x, POSITION_PRECISION),
                "y": round(node.y, POSITION_PRECISION),
            }
    return positions


def editable_nodes(layout: Layout) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    for node in layout.nodes.values():
        if node.kind == "entity":
            nodes.append(
                {
                    "id": node.id,
                    "positionKey": node.id,
                    "domId": escape_id(node.id),
                    "kind": "entity",
                    "label": node.label,
                    "x": round(node.x, 2),
                    "y": round(node.y, 2),
                    "width": round(node.width, 2),
                    "height": round(node.height, 2),
                }
            )
        elif node.kind == "relationship" and node.id.startswith("rel:"):
            rel_id = node.id.removeprefix("rel:")
            nodes.append(
                {
                    "id": node.id,
                    "positionKey": rel_id,
                    "domId": escape_id(node.id),
                    "kind": "relationship",
                    "label": node.label,
                    "x": round(node.x, 2),
                    "y": round(node.y, 2),
                    "width": round(node.width, 2),
                    "height": round(node.height, 2),
                }
            )
    nodes.sort(key=lambda item: (item["kind"], item["label"], item["id"]))
    return nodes


def response_payload(result: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in result.items() if key != "layout"}


def make_handler(editor: WebEditor) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "ERWebEditor/1.0"

        def do_GET(self) -> None:
            path = urlparse(self.path).path
            try:
                if path == "/":
                    self.write_html(editor_page())
                elif path == "/favicon.ico":
                    self.write_empty(HTTPStatus.NO_CONTENT)
                elif path == "/api/state":
                    self.write_json(response_payload(editor.state(write_outputs=False)))
                else:
                    self.send_error(HTTPStatus.NOT_FOUND)
            except Exception as exc:  # noqa: BLE001 - endpoint boundary returns JSON errors.
                self.write_error(exc)

        def do_POST(self) -> None:
            path = urlparse(self.path).path
            try:
                payload = self.read_json()
                if path == "/api/preview":
                    self.write_json(response_payload(editor.preview(payload)))
                elif path == "/api/save":
                    self.write_json(response_payload(editor.save(payload)))
                elif path == "/api/reset":
                    self.write_json(response_payload(editor.reset()))
                else:
                    self.send_error(HTTPStatus.NOT_FOUND)
            except Exception as exc:  # noqa: BLE001 - endpoint boundary returns JSON errors.
                self.write_error(exc)

        def read_json(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0") or "0")
            if length <= 0:
                return {}
            data = self.rfile.read(length)
            try:
                payload = json.loads(data.decode("utf-8"))
            except json.JSONDecodeError as exc:
                raise ERError(f"Invalid JSON payload: {exc}") from exc
            if not isinstance(payload, dict):
                raise ERError("JSON payload must be an object")
            return payload

        def write_html(self, html: str) -> None:
            data = html.encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def write_json(self, payload: dict[str, Any]) -> None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def write_empty(self, status: HTTPStatus) -> None:
            self.send_response(status)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def write_error(self, exc: Exception) -> None:
            status = HTTPStatus.BAD_REQUEST if isinstance(exc, ERError) else HTTPStatus.INTERNAL_SERVER_ERROR
            payload = {"error": str(exc)}
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, format: str, *args: Any) -> None:
            print(f"{self.address_string()} - {format % args}", file=sys.stderr)

    return Handler


def editor_page() -> str:
    return r"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ER Layout Editor</title>
<style>
:root {
  --ink: #1e2528;
  --muted: #647071;
  --paper: #f7f3ea;
  --panel: #fffaf0;
  --line: #272f32;
  --accent: #c54e2d;
  --accent-2: #0f766e;
  --ok: #177245;
  --bad: #a83232;
}
* { box-sizing: border-box; }
html, body { height: 100%; }
body {
  margin: 0;
  background: var(--paper);
  color: var(--ink);
  font-family: "Avenir Next", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
  overflow: hidden;
}
.app {
  display: grid;
  grid-template-columns: 1fr 320px;
  grid-template-rows: 58px 1fr;
  height: 100vh;
}
.toolbar {
  grid-column: 1 / -1;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  background: #202729;
  color: #fff9ec;
  border-bottom: 3px solid #111;
}
.brand {
  font-family: "DIN Alternate", "Avenir Next Condensed", "PingFang SC", sans-serif;
  font-size: 19px;
  letter-spacing: 0;
  margin-right: 12px;
  white-space: nowrap;
}
.button {
  height: 34px;
  border: 1px solid rgba(255,255,255,.26);
  background: #30393b;
  color: #fff9ec;
  padding: 0 12px;
  border-radius: 6px;
  font-size: 13px;
  cursor: pointer;
}
.button:hover { border-color: #fff9ec; background: #3a4547; }
.button.primary { background: var(--accent); border-color: var(--accent); color: #fff; }
.button.ghost { background: transparent; }
.button:disabled { opacity: .45; cursor: default; }
.spacer { flex: 1; }
.status {
  min-width: 260px;
  text-align: right;
  color: #d7ddcf;
  font-size: 12px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.stage {
  position: relative;
  overflow: auto;
  background:
    linear-gradient(#ded7c7 1px, transparent 1px),
    linear-gradient(90deg, #ded7c7 1px, transparent 1px),
    #eee7d8;
  background-size: 28px 28px;
}
.svg-host {
  min-width: 100%;
  min-height: 100%;
  padding: 44px;
  transform-origin: 0 0;
}
.svg-host svg {
  display: block;
  background: #fffdf8;
  box-shadow: 0 24px 60px rgba(32,39,41,.22);
  border: 1px solid #191f21;
}
.svg-host .draggable-node > .entity,
.svg-host .draggable-node > .relationship {
  cursor: grab;
  transition: stroke-width .12s ease, stroke .12s ease, fill .12s ease;
}
.svg-host .draggable-node:hover > .entity,
.svg-host .draggable-node:hover > .relationship {
  stroke: var(--accent);
  stroke-width: 2.6px;
}
.svg-host .dragging > .entity,
.svg-host .dragging > .relationship {
  cursor: grabbing;
  stroke: var(--accent-2);
  stroke-width: 3px;
  fill: #fff8df;
}
.side {
  background: var(--panel);
  border-left: 3px solid #202729;
  display: grid;
  grid-template-rows: auto auto 1fr;
  min-width: 0;
}
.paths, .stats, .nodes {
  padding: 14px;
  border-bottom: 1px solid #d8cdb7;
}
.section-title {
  font-family: "DIN Alternate", "Avenir Next Condensed", "PingFang SC", sans-serif;
  font-size: 13px;
  text-transform: uppercase;
  color: #30393b;
  margin-bottom: 8px;
}
.path-line, .stat-line {
  display: grid;
  grid-template-columns: 78px 1fr;
  gap: 8px;
  font-size: 12px;
  line-height: 1.45;
  margin: 4px 0;
}
.path-line span:last-child {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.stats-grid {
  display: grid;
  grid-template-columns: 1fr 64px;
  gap: 5px 10px;
  font-size: 12px;
}
.metric-ok { color: var(--ok); }
.metric-bad { color: var(--bad); font-weight: 700; }
.nodes {
  overflow: hidden;
  border-bottom: 0;
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.node-list {
  overflow: auto;
  padding-right: 3px;
}
.node-row {
  width: 100%;
  border: 1px solid #dfd3bd;
  background: #fffdf8;
  color: var(--ink);
  border-radius: 6px;
  padding: 8px 9px;
  margin-bottom: 7px;
  text-align: left;
  cursor: pointer;
}
.node-row:hover { border-color: var(--accent); }
.node-row.active { border-color: var(--accent-2); box-shadow: inset 4px 0 0 var(--accent-2); }
.node-name {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  font-size: 13px;
}
.node-kind {
  color: var(--muted);
  font-size: 11px;
}
.node-coord {
  margin-top: 4px;
  color: var(--muted);
  font-family: "DIN Alternate", "Avenir Next Condensed", monospace;
  font-size: 12px;
}
.empty {
  padding: 40px;
  color: var(--muted);
}
@media (max-width: 980px) {
  .app { grid-template-columns: 1fr; grid-template-rows: 58px 1fr 280px; }
  .side { border-left: 0; border-top: 3px solid #202729; }
  .status { display: none; }
}
</style>
</head>
<body>
<div class="app">
  <header class="toolbar">
    <div class="brand">ER Layout Editor</div>
    <button class="button primary" id="saveBtn" title="Save layout and regenerate files">Save</button>
    <button class="button" id="previewBtn" title="Rerender preview from current positions">Preview</button>
    <button class="button ghost" id="resetBtn" title="Reset to automatic layout">Reset</button>
    <button class="button ghost" id="debugBtn" title="Show territory masks and placement order">Debug</button>
    <button class="button" id="fitBtn" title="Fit diagram to the viewport">Fit</button>
    <button class="button" id="zoomOutBtn" title="Zoom out">-</button>
    <button class="button" id="zoomInBtn" title="Zoom in">+</button>
    <div class="spacer"></div>
    <div class="status" id="status">Loading...</div>
  </header>
  <main class="stage" id="stage">
    <div class="svg-host" id="svgHost"><div class="empty">Loading diagram...</div></div>
  </main>
  <aside class="side">
    <section class="paths">
      <div class="section-title">Files</div>
      <div id="paths"></div>
    </section>
    <section class="stats">
      <div class="section-title">Stats</div>
      <div class="stats-grid" id="stats"></div>
    </section>
    <section class="nodes">
      <div class="section-title">Draggable Nodes</div>
      <div class="node-list" id="nodeList"></div>
    </section>
  </aside>
</div>
<script>
const state = {
  positions: { entities: {}, relationships: {} },
  nodes: [],
  selectedId: null,
  zoom: 1,
  debugTerritory: false,
  drag: null,
  busy: false
};

const svgHost = document.getElementById("svgHost");
const stage = document.getElementById("stage");
const statusEl = document.getElementById("status");

function setStatus(message, isError = false) {
  statusEl.textContent = message;
  statusEl.style.color = isError ? "#ffd0c2" : "#d7ddcf";
}

async function requestJson(path, body = null) {
  const options = body ? {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body)
  } : {};
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || response.statusText);
  return data;
}

function currentSvg() {
  return svgHost.querySelector("svg");
}

function applyZoom() {
  svgHost.style.transform = `scale(${state.zoom})`;
}

function syncState(data) {
  state.positions = JSON.parse(JSON.stringify(data.positions));
  state.nodes = data.nodes || [];
  state.debugTerritory = Boolean(data.debugTerritory);
}

function renderAll(data) {
  syncState(data);
  svgHost.innerHTML = data.svg;
  applyZoom();
  wireDraggables();
  renderPaths(data.paths || {});
  renderStats(data.stats || {});
  renderNodeList();
  renderDebugButton();
  if (data.pngError) setStatus(`Saved SVG and layout; PNG failed: ${data.pngError}`, true);
}

function renderDebugButton() {
  const button = document.getElementById("debugBtn");
  button.classList.toggle("primary", state.debugTerritory);
  button.classList.toggle("ghost", !state.debugTerritory);
  button.textContent = state.debugTerritory ? "Debug On" : "Debug";
}

function renderPaths(paths) {
  const rows = [
    ["Input", paths.input],
    ["Layout", paths.layout],
    ["SVG", paths.output],
    ["PNG", paths.png || "disabled"]
  ];
  document.getElementById("paths").innerHTML = rows.map(([label, value]) =>
    `<div class="path-line"><span>${label}</span><span title="${escapeHtml(value || "")}">${escapeHtml(value || "")}</span></div>`
  ).join("");
}

function renderStats(stats) {
  const hardKeys = new Set([
    "relationship_crossings",
    "relationship_obstacle_hits",
    "territory_overlaps",
    "attribute_out_of_territory",
    "relationship_crosses_territory",
    "node_overlaps"
  ]);
  document.getElementById("stats").innerHTML = Object.entries(stats).map(([key, value]) => {
    const cls = hardKeys.has(key) && Number(value) !== 0 ? "metric-bad" : "metric-ok";
    return `<span>${escapeHtml(key)}</span><span class="${cls}">${escapeHtml(String(value))}</span>`;
  }).join("");
}

function renderNodeList() {
  const list = document.getElementById("nodeList");
  list.innerHTML = state.nodes.map(node => {
    const active = node.id === state.selectedId ? " active" : "";
    return `<button class="node-row${active}" data-node="${escapeHtml(node.id)}">
      <div class="node-name"><span>${escapeHtml(node.label)}</span><span class="node-kind">${node.kind}</span></div>
      <div class="node-coord">${node.x.toFixed(2)}, ${node.y.toFixed(2)}</div>
    </button>`;
  }).join("");
  list.querySelectorAll(".node-row").forEach(button => {
    button.addEventListener("click", () => selectNode(button.dataset.node));
  });
}

function wireDraggables() {
  const svg = currentSvg();
  if (!svg) return;
  for (const node of state.nodes) {
    const element = svg.getElementById(node.domId);
    if (!element) continue;
    element.classList.add("draggable-node");
    element.addEventListener("pointerdown", event => startDrag(event, node, element));
  }
}

function selectNode(id) {
  state.selectedId = id;
  renderNodeList();
  const svg = currentSvg();
  if (!svg) return;
  for (const node of state.nodes) {
    const element = svg.getElementById(node.domId);
    if (element) element.classList.toggle("selected-node", node.id === id);
  }
}

function svgPoint(event) {
  const svg = currentSvg();
  const point = svg.createSVGPoint();
  point.x = event.clientX;
  point.y = event.clientY;
  return point.matrixTransform(svg.getScreenCTM().inverse());
}

function startDrag(event, node, element) {
  if (event.button !== 0 || state.busy) return;
  event.preventDefault();
  event.stopPropagation();
  selectNode(node.id);
  const point = svgPoint(event);
  state.drag = {
    node,
    element,
    pointerId: event.pointerId,
    startX: point.x,
    startY: point.y,
    originX: node.x,
    originY: node.y
  };
  element.classList.add("dragging");
  element.setPointerCapture(event.pointerId);
  element.addEventListener("pointermove", moveDrag);
  element.addEventListener("pointerup", endDrag);
  element.addEventListener("pointercancel", cancelDrag);
}

function moveDrag(event) {
  const drag = state.drag;
  if (!drag || event.pointerId !== drag.pointerId) return;
  const point = svgPoint(event);
  const dx = point.x - drag.startX;
  const dy = point.y - drag.startY;
  drag.nextX = drag.originX + dx;
  drag.nextY = drag.originY + dy;
  drag.element.setAttribute("transform", `translate(${dx} ${dy})`);
}

async function endDrag(event) {
  const drag = state.drag;
  if (!drag || event.pointerId !== drag.pointerId) return;
  cleanupDrag();
  const nextX = roundCoord(drag.nextX ?? drag.originX);
  const nextY = roundCoord(drag.nextY ?? drag.originY);
  if (Math.abs(nextX - drag.originX) < 0.5 && Math.abs(nextY - drag.originY) < 0.5) return;
  const group = drag.node.kind === "relationship" ? "relationships" : "entities";
  state.positions[group][drag.node.positionKey] = { x: nextX, y: nextY };
  await preview();
}

function cancelDrag() {
  cleanupDrag();
}

function cleanupDrag() {
  const drag = state.drag;
  if (!drag) return;
  drag.element.classList.remove("dragging");
  drag.element.removeAttribute("transform");
  drag.element.removeEventListener("pointermove", moveDrag);
  drag.element.removeEventListener("pointerup", endDrag);
  drag.element.removeEventListener("pointercancel", cancelDrag);
  state.drag = null;
}

async function preview() {
  await runBusy("Rendering preview...", async () => {
    const data = await requestJson("/api/preview", {
      positions: state.positions,
      debugTerritory: state.debugTerritory
    });
    renderAll(data);
    setStatus("Preview updated");
  });
}

async function save() {
  await runBusy("Saving layout, SVG, and PNG...", async () => {
    const data = await requestJson("/api/save", {
      positions: state.positions,
      debugTerritory: state.debugTerritory
    });
    renderAll(data);
    setStatus("Saved");
  });
}

async function toggleDebug() {
  state.debugTerritory = !state.debugTerritory;
  renderDebugButton();
  await preview();
}

async function resetLayout() {
  if (!window.confirm("Reset to automatic layout?")) return;
  await runBusy("Resetting layout...", async () => {
    const data = await requestJson("/api/reset", {});
    renderAll(data);
    setStatus("Reset to automatic layout");
  });
}

async function runBusy(message, action) {
  if (state.busy) return;
  state.busy = true;
  setButtonsDisabled(true);
  setStatus(message);
  try {
    await action();
  } catch (error) {
    setStatus(error.message || String(error), true);
  } finally {
    state.busy = false;
    setButtonsDisabled(false);
  }
}

function setButtonsDisabled(disabled) {
  for (const id of ["saveBtn", "previewBtn", "resetBtn", "debugBtn"]) {
    document.getElementById(id).disabled = disabled;
  }
}

function fitCanvas() {
  const svg = currentSvg();
  if (!svg) return;
  const width = Number(svg.getAttribute("width")) || svg.viewBox.baseVal.width || 1000;
  const height = Number(svg.getAttribute("height")) || svg.viewBox.baseVal.height || 700;
  const scaleX = (stage.clientWidth - 70) / width;
  const scaleY = (stage.clientHeight - 70) / height;
  state.zoom = Math.max(0.15, Math.min(1.8, Math.min(scaleX, scaleY)));
  applyZoom();
}

function zoomBy(amount) {
  state.zoom = Math.max(0.15, Math.min(3, roundCoord(state.zoom + amount)));
  applyZoom();
}

function roundCoord(value) {
  return Math.round(Number(value) * 100) / 100;
}

function escapeHtml(value) {
  return value.replace(/[&<>"']/g, char => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    "\"": "&quot;",
    "'": "&#39;"
  })[char]);
}

document.getElementById("saveBtn").addEventListener("click", save);
document.getElementById("previewBtn").addEventListener("click", preview);
document.getElementById("resetBtn").addEventListener("click", resetLayout);
document.getElementById("debugBtn").addEventListener("click", toggleDebug);
document.getElementById("fitBtn").addEventListener("click", fitCanvas);
document.getElementById("zoomOutBtn").addEventListener("click", () => zoomBy(-0.1));
document.getElementById("zoomInBtn").addEventListener("click", () => zoomBy(0.1));

window.addEventListener("keydown", event => {
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "s") {
    event.preventDefault();
    save();
  }
});

runBusy("Loading diagram...", async () => {
  const data = await requestJson("/api/state");
  renderAll(data);
  setStatus("Ready");
  window.setTimeout(fitCanvas, 80);
});
</script>
</body>
</html>
"""


def default_output_path(input_path: Path) -> Path:
    return input_path.with_suffix(".svg")


def default_layout_path(output_path: Path) -> Path:
    return output_path.with_suffix(".layout.json")


def default_png_path(output_path: Path) -> Path:
    return output_path.with_name(f"{output_path.stem}@3x.png")


def parse_args(argv: list[str] | None = None) -> WebEditorConfig:
    parser = argparse.ArgumentParser(description="Open a local browser editor for Chen ER diagram positions.")
    parser.add_argument("input", type=Path, help="Input JSON file")
    parser.add_argument("-o", "--output", type=Path, help="Output SVG path")
    parser.add_argument("--layout-output", type=Path, help="Layout JSON path. Default: output path with .layout.json suffix")
    parser.add_argument("--png-output", type=Path, help="PNG output path. Default: output stem plus @3x.png")
    parser.add_argument("--no-png", action="store_true", help="Do not export PNG on save")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host. Default: 127.0.0.1")
    parser.add_argument("--port", type=int, default=8765, help="Bind port. Default: 8765")
    parser.add_argument("--open", action="store_true", help="Open the editor in the default browser")
    parser.add_argument(
        "--post-layout",
        choices=sorted(VALID_POST_LAYOUTS),
        help="Initial automatic post-layout before manual edits. Manual previews/saves use none.",
    )
    parser.add_argument("--debug-territory", action="store_true", help="Draw entity territory circles in the editor SVG")
    parser.add_argument("--target-aspect", type=float, help="Target diagram aspect ratio for automatic layout scoring")
    parser.add_argument("--png-scale", type=float, default=3.0, help="PNG zoom scale when --png-width is not set. Default: 3")
    parser.add_argument("--png-dpi", type=int, default=300, help="PNG DPI metadata/rendering hint. Default: 300")
    parser.add_argument("--png-width", type=int, help="PNG output width in pixels; overrides --png-scale")
    args = parser.parse_args(argv)

    output_path = args.output or default_output_path(args.input)
    png_path = None if args.no_png else args.png_output or default_png_path(output_path)
    if args.target_aspect is not None and args.target_aspect <= 0:
        raise ERError("--target-aspect must be a positive number")
    if args.png_scale <= 0:
        raise ERError("--png-scale must be a positive number")
    if args.png_dpi <= 0:
        raise ERError("--png-dpi must be a positive integer")
    if args.png_width is not None and args.png_width <= 0:
        raise ERError("--png-width must be a positive integer")
    if args.port <= 0:
        raise ERError("--port must be a positive integer")

    return WebEditorConfig(
        input_path=args.input,
        output_path=output_path,
        layout_path=args.layout_output or default_layout_path(output_path),
        png_path=png_path,
        host=args.host,
        port=args.port,
        open_browser=args.open,
        post_layout=args.post_layout,
        debug_territory=args.debug_territory,
        target_aspect=args.target_aspect,
        png_scale=args.png_scale,
        png_dpi=args.png_dpi,
        png_width=args.png_width,
    )


def bind_server(config: WebEditorConfig, editor: WebEditor) -> ThreadingHTTPServer:
    handler = make_handler(editor)
    last_error: OSError | None = None
    for port in range(config.port, config.port + 30):
        try:
            server = ThreadingHTTPServer((config.host, port), handler)
            server.daemon_threads = True
            return server
        except OSError as exc:
            last_error = exc
    raise ERError(f"Cannot bind {config.host}:{config.port}-{config.port + 29}: {last_error}")


def main(argv: list[str] | None = None) -> int:
    try:
        config = parse_args(argv)
        editor = WebEditor(config)
        editor.state(write_outputs=True)
        server = bind_server(config, editor)
        host, port = server.server_address[:2]
        url = f"http://{host}:{port}/"
        print(f"ER editor: {url}")
        print(f"Input: {config.input_path}")
        print(f"Layout: {config.layout_path}")
        print(f"SVG: {config.output_path}")
        if config.png_path is not None:
            print(f"PNG: {config.png_path}")
        if config.open_browser:
            webbrowser.open(url)
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nER editor stopped.")
        return 0
    except ERError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0
