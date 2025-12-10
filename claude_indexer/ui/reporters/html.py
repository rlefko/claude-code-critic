"""HTML reporter for comprehensive UI redesign reports.

Generates rich HTML reports with screenshot galleries,
computed style diffs, and file:line navigation links.
"""

import html
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..critique.engine import CritiqueItem, CritiqueReport
    from ..plan.task import ImplementationPlan, Task, TaskGroup


@dataclass
class HTMLReportConfig:
    """Configuration for HTML report generation."""

    title: str = "UI Redesign Report"
    include_screenshots: bool = True
    include_style_diffs: bool = True
    max_screenshots_per_gallery: int = 6
    max_evidence_per_critique: int = 10
    responsive: bool = True
    theme: str = "light"  # "light" | "dark"


class HTMLReporter:
    """Generates rich HTML reports for /redesign command.

    Creates comprehensive reports with:
    - Screenshot galleries per cluster
    - Computed style diffs highlighted
    - Clickable file:line links
    - Responsive design
    """

    # Severity badge colors
    SEVERITY_COLORS = {
        "fail": "#dc2626",  # Red
        "warn": "#f59e0b",  # Amber
        "info": "#3b82f6",  # Blue
    }

    # Category icons (using unicode)
    CATEGORY_ICONS = {
        "consistency": "\u2261",  # Hamburger/lines
        "hierarchy": "\u25b2",  # Triangle
        "affordance": "\u261b",  # Hand
    }

    def __init__(self, config: HTMLReportConfig | None = None):
        """Initialize the HTML reporter.

        Args:
            config: Optional report configuration.
        """
        self.config = config or HTMLReportConfig()

    def _escape(self, text: str) -> str:
        """HTML escape text."""
        return html.escape(str(text))

    def _render_css(self) -> str:
        """Render CSS styles."""
        theme = self.config.theme
        bg_color = "#ffffff" if theme == "light" else "#1a1a2e"
        text_color = "#1f2937" if theme == "light" else "#e5e7eb"
        card_bg = "#f9fafb" if theme == "light" else "#16213e"
        border_color = "#e5e7eb" if theme == "light" else "#374151"

        return f"""
        <style>
            * {{ box-sizing: border-box; margin: 0; padding: 0; }}
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                line-height: 1.6;
                color: {text_color};
                background-color: {bg_color};
                padding: 2rem;
                max-width: 1200px;
                margin: 0 auto;
            }}
            h1, h2, h3, h4 {{ font-weight: 600; margin-top: 1.5rem; margin-bottom: 0.75rem; }}
            h1 {{ font-size: 2rem; border-bottom: 2px solid {border_color}; padding-bottom: 0.5rem; }}
            h2 {{ font-size: 1.5rem; color: #6366f1; }}
            h3 {{ font-size: 1.25rem; }}

            .summary-card {{
                background: {card_bg};
                border: 1px solid {border_color};
                border-radius: 8px;
                padding: 1.5rem;
                margin: 1rem 0;
            }}
            .summary-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 1rem;
            }}
            .stat {{
                text-align: center;
                padding: 1rem;
                background: {bg_color};
                border-radius: 6px;
            }}
            .stat-value {{
                font-size: 2rem;
                font-weight: 700;
                color: #6366f1;
            }}
            .stat-label {{
                font-size: 0.875rem;
                color: #6b7280;
            }}

            .critique {{
                background: {card_bg};
                border: 1px solid {border_color};
                border-radius: 8px;
                padding: 1.5rem;
                margin: 1rem 0;
                border-left: 4px solid #6366f1;
            }}
            .critique-header {{
                display: flex;
                justify-content: space-between;
                align-items: flex-start;
                margin-bottom: 1rem;
            }}
            .critique-title {{
                font-size: 1.125rem;
                font-weight: 600;
                margin: 0;
            }}
            .badge {{
                display: inline-block;
                padding: 0.25rem 0.75rem;
                border-radius: 9999px;
                font-size: 0.75rem;
                font-weight: 600;
                text-transform: uppercase;
                color: white;
            }}
            .badge-fail {{ background-color: {self.SEVERITY_COLORS['fail']}; }}
            .badge-warn {{ background-color: {self.SEVERITY_COLORS['warn']}; }}
            .badge-info {{ background-color: {self.SEVERITY_COLORS['info']}; }}

            .gallery {{
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
                gap: 0.75rem;
                margin: 1rem 0;
            }}
            .gallery-item {{
                border: 1px solid {border_color};
                border-radius: 4px;
                overflow: hidden;
            }}
            .gallery-item img {{
                width: 100%;
                height: auto;
                display: block;
            }}

            .evidence-list {{
                list-style: none;
                margin: 0.75rem 0;
            }}
            .evidence-list li {{
                padding: 0.5rem;
                background: {bg_color};
                border-radius: 4px;
                margin: 0.25rem 0;
                font-family: 'SF Mono', Monaco, monospace;
                font-size: 0.875rem;
            }}

            .file-link {{
                color: #6366f1;
                text-decoration: none;
                cursor: pointer;
            }}
            .file-link:hover {{
                text-decoration: underline;
            }}

            .style-diff {{
                font-family: 'SF Mono', Monaco, monospace;
                font-size: 0.875rem;
                background: {bg_color};
                border-radius: 4px;
                padding: 1rem;
                overflow-x: auto;
            }}
            .diff-added {{ color: #22c55e; }}
            .diff-removed {{ color: #ef4444; }}
            .diff-changed {{ color: #f59e0b; }}

            .task-group {{
                margin: 1.5rem 0;
            }}
            .task-group-header {{
                background: #6366f1;
                color: white;
                padding: 0.75rem 1rem;
                border-radius: 8px 8px 0 0;
            }}
            .task {{
                background: {card_bg};
                border: 1px solid {border_color};
                border-top: none;
                padding: 1rem;
            }}
            .task:last-child {{
                border-radius: 0 0 8px 8px;
            }}
            .task-header {{
                display: flex;
                justify-content: space-between;
                align-items: center;
            }}
            .task-title {{
                font-weight: 600;
            }}
            .task-meta {{
                font-size: 0.875rem;
                color: #6b7280;
            }}
            .task-criteria {{
                list-style: disc;
                margin-left: 1.5rem;
                margin-top: 0.5rem;
            }}
            .task-criteria li {{
                margin: 0.25rem 0;
            }}

            .quick-wins {{
                background: linear-gradient(135deg, #22c55e22, #16a34a22);
                border: 1px solid #22c55e;
                border-radius: 8px;
                padding: 1.5rem;
                margin: 1rem 0;
            }}
            .quick-wins-title {{
                color: #16a34a;
                margin-top: 0;
            }}

            .hints {{
                background: #eff6ff;
                border-left: 4px solid #3b82f6;
                padding: 1rem;
                margin: 0.75rem 0;
                border-radius: 0 4px 4px 0;
            }}
            .hints-title {{
                font-weight: 600;
                color: #1d4ed8;
                margin-bottom: 0.5rem;
            }}
            .hints ul {{
                margin-left: 1.25rem;
            }}

            footer {{
                margin-top: 3rem;
                padding-top: 1rem;
                border-top: 1px solid {border_color};
                text-align: center;
                color: #6b7280;
                font-size: 0.875rem;
            }}

            @media (max-width: 768px) {{
                body {{ padding: 1rem; }}
                .summary-grid {{ grid-template-columns: 1fr 1fr; }}
                .gallery {{ grid-template-columns: repeat(2, 1fr); }}
            }}
        </style>
        """

    def _render_header(self, critique_report: "CritiqueReport") -> str:
        """Render report header with summary."""
        summary = critique_report.summary

        return f"""
        <header>
            <h1>{self._escape(self.config.title)}</h1>
            <p>Generated: {critique_report.generated_at}</p>

            <div class="summary-card">
                <div class="summary-grid">
                    <div class="stat">
                        <div class="stat-value">{summary.total_critiques}</div>
                        <div class="stat-label">Total Issues</div>
                    </div>
                    <div class="stat">
                        <div class="stat-value">{summary.token_adherence_rate:.0%}</div>
                        <div class="stat-label">Token Adherence</div>
                    </div>
                    <div class="stat">
                        <div class="stat-value">{summary.accessibility_issues}</div>
                        <div class="stat-label">Accessibility Issues</div>
                    </div>
                    <div class="stat">
                        <div class="stat-value">{critique_report.statistics.elements_analyzed}</div>
                        <div class="stat-label">Elements Analyzed</div>
                    </div>
                </div>
            </div>
        </header>
        """

    def _render_critique(self, critique: "CritiqueItem") -> str:
        """Render single critique item."""
        severity_class = f"badge-{critique.severity.value}"
        icon = self.CATEGORY_ICONS.get(critique.category, "")

        # Build evidence list
        evidence_html = ""
        if critique.evidence:
            evidence_items = []
            for ev in critique.evidence[: self.config.max_evidence_per_critique]:
                if ev.source_ref:
                    link = self._render_file_link(
                        ev.source_ref.file_path, ev.source_ref.start_line
                    )
                    evidence_items.append(f"<li>{link}: {self._escape(ev.description)}</li>")
                else:
                    evidence_items.append(f"<li>{self._escape(ev.description)}</li>")
            if evidence_items:
                evidence_html = f'<ul class="evidence-list">{"".join(evidence_items)}</ul>'

        # Build screenshot gallery
        gallery_html = ""
        if self.config.include_screenshots and critique.screenshots:
            screenshots = critique.screenshots[: self.config.max_screenshots_per_gallery]
            gallery_items = "".join(
                f'<div class="gallery-item"><img src="{self._escape(s)}" alt="Screenshot"></div>'
                for s in screenshots
            )
            gallery_html = f'<div class="gallery">{gallery_items}</div>'

        # Build hints section
        hints_html = ""
        if critique.remediation_hints:
            hints_items = "".join(
                f"<li>{self._escape(hint)}</li>" for hint in critique.remediation_hints
            )
            hints_html = f"""
            <div class="hints">
                <div class="hints-title">Recommended Actions</div>
                <ul>{hints_items}</ul>
            </div>
            """

        return f"""
        <div class="critique" style="border-left-color: {self.SEVERITY_COLORS.get(critique.severity.value, '#6366f1')}">
            <div class="critique-header">
                <h3 class="critique-title">{icon} {self._escape(critique.title)}</h3>
                <span class="badge {severity_class}">{critique.severity.value.upper()}</span>
            </div>
            <p>{self._escape(critique.description)}</p>
            {gallery_html}
            {evidence_html}
            {hints_html}
        </div>
        """

    def _render_file_link(self, file_path: str, line: int) -> str:
        """Render clickable file:line link."""
        display = f"{file_path}:{line}"
        # Use vscode:// URL scheme for click-to-open
        vscode_url = f"vscode://file/{file_path}:{line}"
        return f'<a class="file-link" href="{vscode_url}">{self._escape(display)}</a>'

    def _render_style_diff(
        self, style1: dict[str, str], style2: dict[str, str], label1: str, label2: str
    ) -> str:
        """Render highlighted style differences."""
        if not self.config.include_style_diffs:
            return ""

        all_props = set(style1.keys()) | set(style2.keys())
        diff_lines = []

        for prop in sorted(all_props):
            val1 = style1.get(prop, "(none)")
            val2 = style2.get(prop, "(none)")

            if val1 == val2:
                diff_lines.append(f"  {prop}: {val1}")
            elif prop not in style1:
                diff_lines.append(f'<span class="diff-added">+ {prop}: {val2}</span>')
            elif prop not in style2:
                diff_lines.append(f'<span class="diff-removed">- {prop}: {val1}</span>')
            else:
                diff_lines.append(
                    f'<span class="diff-changed">~ {prop}: {val1} → {val2}</span>'
                )

        diff_content = "<br>".join(diff_lines)

        return f"""
        <div class="style-diff">
            <strong>{self._escape(label1)} vs {self._escape(label2)}</strong>
            <pre>{diff_content}</pre>
        </div>
        """

    def _render_critiques_section(self, critique_report: "CritiqueReport") -> str:
        """Render all critiques grouped by category."""
        sections = []

        for category in ["consistency", "hierarchy", "affordance"]:
            critiques = critique_report.get_critiques_by_category(category)
            if not critiques:
                continue

            icon = self.CATEGORY_ICONS.get(category, "")
            critique_items = "".join(self._render_critique(c) for c in critiques)

            sections.append(f"""
            <section>
                <h2>{icon} {category.title()} Issues ({len(critiques)})</h2>
                {critique_items}
            </section>
            """)

        return "".join(sections)

    def _render_task(self, task: "Task", index: int) -> str:
        """Render single task."""
        criteria_items = "".join(
            f"<li>{self._escape(c)}</li>" for c in task.acceptance_criteria
        )
        criteria_html = f'<ul class="task-criteria">{criteria_items}</ul>' if criteria_items else ""

        quick_win_badge = (
            '<span class="badge" style="background-color: #22c55e; margin-left: 0.5rem;">Quick Win</span>'
            if task.is_quick_win
            else ""
        )

        return f"""
        <div class="task">
            <div class="task-header">
                <span class="task-title">{index}. {self._escape(task.title)} {quick_win_badge}</span>
                <span class="task-meta">Impact: {task.impact:.0%} | Effort: {task.estimated_effort}</span>
            </div>
            <p style="margin-top: 0.5rem; color: #6b7280;">{self._escape(task.description[:200])}...</p>
            {criteria_html}
        </div>
        """

    def _render_task_group(self, group: "TaskGroup") -> str:
        """Render task group."""
        task_items = "".join(
            self._render_task(task, i + 1) for i, task in enumerate(group.tasks)
        )

        return f"""
        <div class="task-group">
            <div class="task-group-header">
                <strong>{group.scope.upper()}</strong>: {self._escape(group.description)}
                ({len(group.tasks)} tasks, {group.total_effort} effort)
            </div>
            {task_items}
        </div>
        """

    def _render_quick_wins(self, plan: "ImplementationPlan") -> str:
        """Render quick wins section."""
        if not plan.quick_wins:
            return ""

        wins_list = "".join(
            f"<li><strong>{self._escape(t.title)}</strong> - {t.impact:.0%} impact</li>"
            for t in plan.quick_wins
        )

        return f"""
        <div class="quick-wins">
            <h3 class="quick-wins-title">Quick Wins</h3>
            <p>High-impact, low-effort tasks to start with:</p>
            <ul style="margin-left: 1.25rem; margin-top: 0.5rem;">{wins_list}</ul>
        </div>
        """

    def _render_plan_section(self, plan: "ImplementationPlan") -> str:
        """Render implementation plan section."""
        quick_wins = self._render_quick_wins(plan)
        groups = "".join(self._render_task_group(g) for g in plan.groups)

        return f"""
        <section>
            <h2>Implementation Plan</h2>
            <p>{self._escape(plan.summary)}</p>
            {quick_wins}
            {groups}
        </section>
        """

    def _render_footer(self) -> str:
        """Render report footer."""
        return f"""
        <footer>
            <p>Generated by UI Consistency Guard | Claude Code Memory</p>
            <p>{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        </footer>
        """

    def generate(
        self,
        critique_report: "CritiqueReport",
        plan: "ImplementationPlan",
        output_path: Path,
    ) -> Path:
        """Generate complete HTML report.

        Args:
            critique_report: Critique report with design issues.
            plan: Implementation plan with tasks.
            output_path: Path to write HTML file.

        Returns:
            Path to generated HTML file.
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Build HTML document
        html_content = f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>{self._escape(self.config.title)}</title>
            {self._render_css()}
        </head>
        <body>
            {self._render_header(critique_report)}
            {self._render_critiques_section(critique_report)}
            {self._render_plan_section(plan)}
            {self._render_footer()}
        </body>
        </html>
        """

        # Write to file
        output_path.write_text(html_content, encoding="utf-8")

        return output_path

    def generate_json(
        self,
        critique_report: "CritiqueReport",
        plan: "ImplementationPlan",
    ) -> str:
        """Generate JSON representation for API consumption.

        Args:
            critique_report: Critique report.
            plan: Implementation plan.

        Returns:
            JSON string.
        """
        return json.dumps(
            {
                "critique_report": critique_report.to_dict(),
                "plan": plan.to_dict(),
            },
            indent=2,
        )


__all__ = [
    "HTMLReporter",
    "HTMLReportConfig",
]
