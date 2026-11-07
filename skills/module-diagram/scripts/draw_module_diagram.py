#!/usr/bin/env python3
"""Draw thesis-style function module diagram from JSON tree."""

import argparse
import json
import math
import os
import sys

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
H_BOX_PAD_X = 12       # horizontal padding inside horizontal (root/intermediate) boxes
H_BOX_PAD_Y = 6        # vertical padding
H_BOX_CHAR_W = 14      # width per character for horizontal labels
H_BOX_HEIGHT = 28      # fixed height for horizontal boxes

V_BOX_WIDTH = 28       # width for vertical (leaf) boxes
V_BOX_CHAR_H = 18      # height per character line for vertical labels
V_BOX_PAD_Y = 6        # top/bottom padding inside vertical boxes

LEVEL_GAP = 40         # vertical gap between levels
SIBLING_GAP = 16       # horizontal gap between siblings
STROKE_WIDTH = 1.5
FONT_SIZE_H = 13       # font size for horizontal boxes
FONT_SIZE_V = 13       # font size for vertical boxes

COLOR_FILL = "#FFFFFF"
COLOR_STROKE = "#000000"
COLOR_TEXT = "#000000"

# ---------------------------------------------------------------------------
# Tree helpers
# ---------------------------------------------------------------------------

def load_tree(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def is_leaf(node):
    return isinstance(node, str) or "children" not in node


def label_of(node):
    if isinstance(node, str):
        return node
    return node.get("label", "")


def children_of(node):
    if isinstance(node, str):
        return []
    return node.get("children", [])


# ---------------------------------------------------------------------------
# Layout – compute (x, y, w, h) for every node
# ---------------------------------------------------------------------------

def max_leaf_len_at_depth(node, depth=0, cache=None):
    """Return the length of the longest leaf label at *depth*."""
    if cache is None:
        cache = {}
    if depth not in cache:
        cache[depth] = 0
    if is_leaf(node):
        cache[depth] = max(cache[depth], len(label_of(node)))
        return cache
    for ch in children_of(node):
        max_leaf_len_at_depth(ch, depth + 1, cache)
    return cache


def leaf_box_height(label_len):
    return V_BOX_PAD_Y * 2 + label_len * V_BOX_CHAR_H


class Box:
    """A positioned rectangle for a node."""
    __slots__ = ("x", "y", "w", "h", "label", "is_leaf", "children_boxes")

    def __init__(self, x, y, w, h, label, is_leaf):
        self.x = x
        self.y = y
        self.w = w
        self.h = h
        self.label = label
        self.is_leaf = is_leaf
        self.children_boxes = []

    @property
    def cx(self):
        return self.x + self.w / 2

    @property
    def cy(self):
        return self.y + self.h / 2

    @property
    def bottom(self):
        return self.y + self.h


def layout_subtree(node, depth, leaf_heights):
    """Return (Box, total_width) for the subtree rooted at *node*."""
    lbl = label_of(node)
    leaf = is_leaf(node)

    if leaf:
        h = leaf_heights.get(depth, leaf_box_height(len(lbl)))
        w = V_BOX_WIDTH
        return Box(0, 0, w, h, lbl, True), w

    ch_nodes = children_of(node)
    ch_boxes = []
    ch_widths = []
    for ch in ch_nodes:
        cb, cw = layout_subtree(ch, depth + 1, leaf_heights)
        ch_boxes.append(cb)
        ch_widths.append(cw)

    # Total width needed for children + gaps
    total_ch_w = sum(ch_widths) + SIBLING_GAP * (len(ch_widths) - 1)

    # Parent box width
    pw = max(total_ch_w, len(lbl) * H_BOX_CHAR_W + H_BOX_PAD_X * 2)
    ph = H_BOX_HEIGHT

    parent = Box(0, 0, pw, ph, lbl, False)

    # Position children relative to parent
    # Center children group under parent
    start_x = (pw - total_ch_w) / 2
    cur_x = start_x
    for i, cb in enumerate(ch_boxes):
        cb.x = cur_x + (ch_widths[i] - cb.w) / 2  # center each child in its slot
        cb.y = ph + LEVEL_GAP
        cur_x += ch_widths[i] + SIBLING_GAP
        parent.children_boxes.append(cb)

    return parent, max(pw, total_ch_w)


def apply_offset(box, dx, dy):
    box.x += dx
    box.y += dy
    for cb in box.children_boxes:
        apply_offset(cb, dx, dy)


# ---------------------------------------------------------------------------
# SVG output
# ---------------------------------------------------------------------------

def svg_escape(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render_box_svg(box):
    """Return list of SVG element strings for box and its descendants."""
    parts = []

    if box.is_leaf:
        # Vertical box: one character per line
        rx = box.x
        ry = box.y
        w = box.w
        h = box.h
        parts.append(
            f'  <rect x="{rx}" y="{ry}" width="{w}" height="{h}" '
            f'fill="{COLOR_FILL}" stroke="{COLOR_STROKE}" stroke-width="{STROKE_WIDTH}" rx="2"/>'
        )
        # Characters centered
        chars = box.label
        total_text_h = len(chars) * V_BOX_CHAR_H
        start_y = ry + (h - total_text_h) / 2 + V_BOX_CHAR_H * 0.8
        for ci, ch in enumerate(chars):
            tx = rx + w / 2
            ty = start_y + ci * V_BOX_CHAR_H
            parts.append(
                f'  <text x="{tx}" y="{ty}" text-anchor="middle" '
                f'font-size="{FONT_SIZE_V}" fill="{COLOR_TEXT}" '
                f'font-family="SimSun, STSong, serif">{svg_escape(ch)}</text>'
            )
    else:
        # Horizontal box
        rx = box.x
        ry = box.y
        w = box.w
        h = box.h
        parts.append(
            f'  <rect x="{rx}" y="{ry}" width="{w}" height="{h}" '
            f'fill="{COLOR_FILL}" stroke="{COLOR_STROKE}" stroke-width="{STROKE_WIDTH}" rx="2"/>'
        )
        tx = rx + w / 2
        ty = ry + h / 2 + FONT_SIZE_H * 0.35
        parts.append(
            f'  <text x="{tx}" y="{ty}" text-anchor="middle" '
            f'font-size="{FONT_SIZE_H}" fill="{COLOR_TEXT}" '
            f'font-family="SimHei, STHeiti, sans-serif">{svg_escape(box.label)}</text>'
        )

    # Connectors to children
    if box.children_boxes:
        n = len(box.children_boxes)
        parent_bottom_x = box.cx
        parent_bottom_y = box.bottom

        # Anchor x: middle child (or average of two middle for even count)
        if n % 2 == 1:
            anchor_x = box.children_boxes[n // 2].cx
        else:
            m1 = box.children_boxes[n // 2 - 1].cx
            m2 = box.children_boxes[n // 2].cx
            anchor_x = (m1 + m2) / 2

        # Vertical line from parent bottom to bus
        bus_y = parent_bottom_y + LEVEL_GAP / 2
        parts.append(
            f'  <line x1="{anchor_x}" y1="{parent_bottom_y}" x2="{anchor_x}" '
            f'y2="{bus_y}" stroke="{COLOR_STROKE}" stroke-width="{STROKE_WIDTH}"/>'
        )

        # Horizontal bus
        left_x = box.children_boxes[0].cx
        right_x = box.children_boxes[-1].cx
        if left_x != right_x:
            parts.append(
                f'  <line x1="{left_x}" y1="{bus_y}" x2="{right_x}" '
                f'y2="{bus_y}" stroke="{COLOR_STROKE}" stroke-width="{STROKE_WIDTH}"/>'
            )

        # Vertical lines from bus to each child top
        for cb in box.children_boxes:
            parts.append(
                f'  <line x1="{cb.cx}" y1="{bus_y}" x2="{cb.cx}" '
                f'y2="{cb.y}" stroke="{COLOR_STROKE}" stroke-width="{STROKE_WIDTH}"/>'
            )

    # Recurse
    for cb in box.children_boxes:
        parts.extend(render_box_svg(cb))

    return parts


def build_svg(root_box):
    margin = 20
    w = root_box.x + root_box.w + margin * 2
    # Find total height
    max_y = root_box.y + root_box.h

    def find_max_y(b):
        nonlocal max_y
        if b.y + b.h > max_y:
            max_y = b.y + b.h
        for cb in b.children_boxes:
            find_max_y(cb)

    find_max_y(root_box)

    h = max_y + margin * 2

    apply_offset(root_box, margin, margin)

    # Recalc after offset
    max_y2 = root_box.y + root_box.h
    find_max_y2 = max_y2
    def _find_max(b):
        nonlocal find_max_y2
        if b.y + b.h > find_max_y2:
            find_max_y2 = b.y + b.h
        for cb in b.children_boxes:
            _find_max(cb)
    _find_max(root_box)

    svg_w = find_max_y2 + margin * 2  # Oops, should be width
    # Actually let me just compute properly
    actual_w = 0
    actual_h = 0
    def _bounds(b):
        nonlocal actual_w, actual_h
        if b.x + b.w > actual_w:
            actual_w = b.x + b.w
        if b.y + b.h > actual_h:
            actual_h = b.y + b.h
        for cb in b.children_boxes:
            _bounds(cb)
    _bounds(root_box)

    svg_w = actual_w + margin
    svg_h = actual_h + margin

    elements = render_box_svg(root_box)

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{svg_w}" height="{svg_h}" '
        f'viewBox="0 0 {svg_w} {svg_h}">\n'
        + "\n".join(elements) + "\n"
        + "</svg>"
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Draw module diagram")
    parser.add_argument("--config", required=True, help="JSON tree file")
    parser.add_argument("--output", required=True, help="Output SVG path")
    parser.add_argument("--png", default=None, help="Optional PNG output path")
    args = parser.parse_args()

    tree = load_tree(args.config)

    # Compute leaf heights per depth
    depth_lens = max_leaf_len_at_depth(tree)
    leaf_heights = {d: leaf_box_height(l) for d, l in depth_lens.items()}

    root_box, total_w = layout_subtree(tree, 0, leaf_heights)

    svg = build_svg(root_box)

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(svg)
    print(f"SVG saved to {args.output}")

    if args.png:
        try:
            import cairosvg
            cairosvg.svg2png(url=args.output, write_to=args.png)
            print(f"PNG saved to {args.png}")
        except ImportError:
            # fallback to rsvg-convert
            ret = os.system(f'rsvg-convert -f png -o "{args.png}" "{args.output}"')
            if ret == 0:
                print(f"PNG saved to {args.png}")
            else:
                print("WARNING: Neither cairosvg nor rsvg-convert available; PNG not generated.",
                      file=sys.stderr)


if __name__ == "__main__":
    main()
