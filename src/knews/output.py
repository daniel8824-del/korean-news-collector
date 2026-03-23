"""검색 결과 출력 포맷터 - 터미널, CSV, JSON, Markdown"""

import csv
import json
import io
from datetime import datetime
from pathlib import Path
from dataclasses import asdict

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.markdown import Markdown

console = Console()


def _prepare_output_path(filepath: str) -> Path:
    """저장 경로의 부모 디렉토리를 미리 생성."""
    path = Path(filepath)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def print_results(articles: list, query: str = ""):
    """터미널에 결과를 예쁘게 출력."""
    if not articles:
        console.print("[yellow]검색 결과가 없습니다.[/yellow]")
        return

    success = [a for a in articles if a.get("success", True)]
    failed = [a for a in articles if not a.get("success", True)]

    console.print()
    console.print(Panel(
        f"[bold]검색어:[/bold] {query}\n"
        f"[bold]결과:[/bold] {len(articles)}건  "
        f"[green]성공 {len(success)}[/green]  "
        f"[red]실패 {len(failed)}[/red]  "
        f"[dim]{datetime.now().strftime('%Y-%m-%d %H:%M')}[/dim]",
        title="[bold blue]뉴스 수집 결과[/bold blue]",
        border_style="blue",
    ))

    for i, a in enumerate(articles, 1):
        title = a.get("title", "(제목 없음)")
        url = a.get("url", "")
        content = a.get("content", "")
        source = a.get("source", "")
        method = a.get("method", "")
        length = a.get("content_length", len(content))
        ok = a.get("success", True)

        status = "[green]OK[/green]" if ok else "[red]FAIL[/red]"
        source_tag = f" [dim]({source})[/dim]" if source else ""
        method_tag = f" [dim][{method}][/dim]" if method else ""

        console.print(f"\n  {status} [bold]{i}. {title}[/bold]{source_tag}{method_tag}")
        console.print(f"     [link={url}]{url}[/link]")

        if ok and content:
            preview = content[:200].replace("\n", " ")
            if len(content) > 200:
                preview += "..."
            console.print(f"     [dim]{preview}[/dim]")
            console.print(f"     [cyan]{length:,}자[/cyan]")
        elif not ok:
            error = a.get("error", "")
            if error:
                console.print(f"     [red]{error}[/red]")

    console.print()


def to_csv(articles: list, filepath: str | None = None) -> str:
    """CSV 형식으로 변환. filepath가 있으면 파일로 저장."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["번호", "제목", "URL", "출처", "본문길이", "추출방법", "성공", "본문"])

    for i, a in enumerate(articles, 1):
        writer.writerow([
            i,
            a.get("title", ""),
            a.get("url", ""),
            a.get("source", ""),
            a.get("content_length", 0),
            a.get("method", ""),
            "O" if a.get("success", True) else "X",
            a.get("content", ""),
        ])

    csv_text = output.getvalue()

    if filepath:
        path = _prepare_output_path(filepath)
        path.write_text(csv_text, encoding="utf-8-sig")
        console.print(f"[green]CSV 저장: {filepath}[/green]")

    return csv_text


def to_json(articles: list, filepath: str | None = None) -> str:
    """JSON 형식으로 변환."""
    data = {
        "collected_at": datetime.now().isoformat(),
        "count": len(articles),
        "articles": articles,
    }
    json_text = json.dumps(data, ensure_ascii=False, indent=2)

    if filepath:
        path = _prepare_output_path(filepath)
        path.write_text(json_text, encoding="utf-8")
        console.print(f"[green]JSON 저장: {filepath}[/green]")

    return json_text


def to_markdown(articles: list, query: str = "", filepath: str | None = None) -> str:
    """Markdown 형식으로 변환."""
    lines = [
        f"# 뉴스 수집: {query}",
        f"",
        f"> 수집일시: {datetime.now().strftime('%Y-%m-%d %H:%M')}  ",
        f"> 결과: {len(articles)}건",
        "",
    ]

    for i, a in enumerate(articles, 1):
        title = a.get("title", "(제목 없음)")
        url = a.get("url", "")
        content = a.get("content", "")
        source = a.get("source", "")
        ok = a.get("success", True)

        lines.append(f"## {i}. {title}")
        lines.append(f"")
        lines.append(f"- 출처: {source}")
        lines.append(f"- URL: {url}")
        lines.append(f"- 상태: {'성공' if ok else '실패'}")
        lines.append(f"")

        if ok and content:
            lines.append(f"```")
            lines.append(content[:2000])
            if len(content) > 2000:
                lines.append(f"... (총 {len(content):,}자)")
            lines.append(f"```")
        lines.append("")

    md_text = "\n".join(lines)

    if filepath:
        path = _prepare_output_path(filepath)
        path.write_text(md_text, encoding="utf-8")
        console.print(f"[green]Markdown 저장: {filepath}[/green]")

    return md_text
