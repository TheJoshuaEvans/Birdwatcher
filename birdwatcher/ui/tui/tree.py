"""
The findings tree: grouped findings, with branches that fold and rows that open.

Joshua Evans, 2026-11-10 (written with Claude Opus 5.5)
"""

from dataclasses import dataclass

from rich.text import Text
from textual.widgets import Tree

from birdwatcher.ui.tui.grouping import Group
from birdwatcher.ui.tui.rows import Row

LABEL_WIDTH = 8  # wide enough for "WARNING" and "IGNORED"
LINE_WIDTH = 5


@dataclass(frozen=True)
class BranchKey:
    """What identifies a branch across rebuilds: its label and its parents'."""

    labels: tuple[str, ...]


class FindingsTree(Tree):
    """
    The findings, grouped into branches (see grouping.group_rows). Branches
    start unfolded; one that is folded stays folded when the tree is shown
    again (matched by its label and its parents' labels).

    Each branch shows its label and how many findings it holds; each row shows
    its severity (or FIXED or IGNORED), its line and its message. Clicking a
    branch folds or unfolds it. Clicking a row highlights it; clicking the
    highlighted row again selects it (Tree.NodeSelected), as Enter does, so a
    single click never opens anything.

    Args:
        id (str | None): The widget's id.
    """

    def __init__(self, *, id=None):
        super().__init__("Findings", id=id)
        self.show_root = False

    def show(self, nodes, keep=None):
        """
        Replace the tree's contents.

        Args:
            nodes (Sequence[Group | Row]): The top-level branches and rows.
            keep (tuple | None): The key (Row.key) of the row to put the
                cursor on. When that row is gone (or None), the cursor goes to
                the row at the same position as the previous cursor row, or the
                last row if there are fewer now.
        """
        before = self.row_nodes()
        position = before.index(self.cursor_node) if self.cursor_node in before else 0
        folded = {node.data for node in self._branch_nodes() if not node.is_expanded}
        self.clear()
        for node in nodes:
            self._add(self.root, node, (), folded)
        rows = self.row_nodes()
        if not rows:
            return
        # Node line numbers are computed lazily; asking for the last line makes
        # the tree compute them, so move_cursor below finds the node's line.
        _ = self.last_line
        target = next((n for n in rows if n.data.key == keep), None)
        self.move_cursor(target or rows[min(position, len(rows) - 1)])

    def row_nodes(self):
        """
        The nodes of the rows that are showing (not in folded branches).

        Returns:
            list[TreeNode]: In display order; each one's data is its Row.
        """
        found = []

        def walk(node):
            for child in node.children:
                if isinstance(child.data, Row):
                    found.append(child)
                elif child.is_expanded:
                    walk(child)

        walk(self.root)
        return found

    def current_row(self):
        """
        The row under the cursor.

        Returns:
            Row | None: None when the cursor is on a branch or nowhere.
        """
        node = self.cursor_node
        return node.data if node is not None and isinstance(node.data, Row) else None

    def step(self, offset):
        """
        Move the cursor to the next (offset 1) or previous (-1) row, skipping
        branches; stays put at either end.

        Args:
            offset (int): 1 or -1.
        """
        rows = self.row_nodes()
        if not rows:
            return
        if self.cursor_node in rows:
            index = rows.index(self.cursor_node) + offset
        else:
            # On a branch: the next row is the first one after the cursor line.
            after = [n for n in rows if (n.line > self.cursor_line) == (offset > 0)]
            index = rows.index(after[0] if offset > 0 else after[-1]) if after else -1
        if 0 <= index < len(rows):
            self.move_cursor(rows[index])

    def fold_level(self):
        """
        Fold the deepest level of branches that has unfolded branches showing
        (a branch's level is how many branches it is inside). The cursor moves
        to the nearest node still showing.
        """
        current = self.cursor_node
        levels = self._showing_branches()
        for depth in sorted(levels, reverse=True):
            unfolded = [node for node in levels[depth] if node.is_expanded]
            if unfolded:
                for node in unfolded:
                    node.collapse()
                break
        while current is not None and not self._is_showing(current):
            current = current.parent
        self._put_cursor(current)

    def unfold_level(self):
        """Unfold the shallowest level of branches that has folded branches
        showing; the cursor stays on its node."""
        current = self.cursor_node
        levels = self._showing_branches()
        for depth in sorted(levels):
            folded = [node for node in levels[depth] if not node.is_expanded]
            if folded:
                for node in folded:
                    node.expand()
                break
        self._put_cursor(current)

    def _showing_branches(self):
        """{level: [branch nodes showing at that level]}."""
        levels = {}

        def walk(node, depth):
            for child in node.children:
                if isinstance(child.data, BranchKey):
                    levels.setdefault(depth, []).append(child)
                    if child.is_expanded:
                        walk(child, depth + 1)

        walk(self.root, 0)
        return levels

    def _is_showing(self, node):
        """Whether every branch around a node is unfolded."""
        parent = node.parent
        while parent is not None and parent != self.root:
            if not parent.is_expanded:
                return False
            parent = parent.parent
        return True

    def _put_cursor(self, node):
        if node is not None and node != self.root:
            _ = self.last_line  # see show(): makes the tree compute node lines
            self.move_cursor(node)

    def _branch_nodes(self):
        """Every branch node, folded or not."""
        found = []

        def walk(node):
            for child in node.children:
                if isinstance(child.data, BranchKey):
                    found.append(child)
                    walk(child)

        walk(self.root)
        return found

    def _add(self, parent, node, parents, folded):
        if isinstance(node, Group):
            label = Text(node.label, style="bold")
            label.append(f"  {node.count}", style="dim")
            key = BranchKey((*parents, node.label))
            branch = parent.add(label, data=key, expand=key not in folded)
            for child in node.children:
                self._add(branch, child, key.labels, folded)
        else:
            parent.add_leaf(_row_label(node), data=node)

    async def _on_click(self, event):
        # Replaces Tree's click handling, which selects on every click. Textual
        # runs the handlers of every class in the hierarchy; prevent_default
        # stops Tree's own from running after this one.
        event.prevent_default()
        async with self.lock:
            meta = event.style.meta
            if "line" not in meta:
                return
            line = meta["line"]
            node = self.get_node_at_line(line)
            if node is None:
                return
            if not isinstance(node.data, Row):
                self.cursor_line = line
                node.toggle()
            elif line == self.cursor_line:
                self.post_message(Tree.NodeSelected(node))
            else:
                self.cursor_line = line


def _row_label(row):
    label, style = row.label
    finding = row.finding
    line = "" if finding.line is None else str(finding.line)
    text = Text(f"{label:<{LABEL_WIDTH}}", style=style)
    text.append(f"{line:>{LINE_WIDTH}}  ")
    text.append(finding.message)
    return text
