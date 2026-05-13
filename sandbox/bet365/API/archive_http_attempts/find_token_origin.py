from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from common import ensure_dir, iter_jsonl

API_ROOT = Path(__file__).resolve().parent
SEARCH_TERMS = (
    "X-Net-Sync-Term",
    "Net-Sync",
    "sync-term",
    "x-request-id",
    "matchmarketscontentapi",
    "matchbettingcontentapi",
    "cf_clearance",
    "pstk",
    "swt",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Busca posibles orígenes de X-Net-Sync-Term y tokens relacionados en archivos locales.",
    )
    parser.add_argument(
        "--roots",
        nargs="*",
        default=[
            str(API_ROOT / "captures"),
            str(API_ROOT / "archive"),
        ],
        help="Directorios raíz a inspeccionar.",
    )
    parser.add_argument(
        "--download-public-scripts",
        action="store_true",
        help="Intenta descargar scripts públicos detectados en capturas.",
    )
    parser.add_argument(
        "--scripts-cache-dir",
        default=str(API_ROOT / "scripts_cache"),
    )
    parser.add_argument(
        "--out",
        default=str(API_ROOT / "output" / "token_origin_report.json"),
    )
    return parser.parse_args()


def iter_candidate_files(roots: list[Path]) -> list[Path]:
    candidates: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() in {".txt", ".js", ".json", ".jsonl", ".html"}:
                candidates.append(path)
    return candidates


def file_matches(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8", errors="replace")
    lowered = text.lower()
    matches: list[dict[str, Any]] = []
    for term in SEARCH_TERMS:
        idx = lowered.find(term.lower())
        if idx == -1:
            continue
        matches.append(
            {
                "term": term,
                "index": idx,
                "snippet": text[max(0, idx - 120): idx + 280],
            }
        )
    return matches


def extract_script_urls(roots: list[Path]) -> list[str]:
    urls: list[str] = []
    for root in roots:
        for network_file in root.rglob("network.jsonl"):
            for record in iter_jsonl(network_file):
                if record.get("resource_type") != "script":
                    continue
                url = record.get("url")
                if isinstance(url, str) and url.startswith("http"):
                    urls.append(url)
    return sorted(dict.fromkeys(urls))


def maybe_download_scripts(script_urls: list[str], cache_dir: Path) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    try:
        import httpx
    except Exception as error:  # noqa: BLE001
        return [{"error": f"httpx unavailable: {type(error).__name__}: {error}"}]

    ensure_dir(cache_dir)
    with httpx.Client(timeout=20.0, follow_redirects=True) as client:
        for index, url in enumerate(script_urls[:20], start=1):
            try:
                response = client.get(url)
                target = cache_dir / f"script-{index:03d}.txt"
                target.write_text(response.text, encoding="utf-8")
                results.append(
                    {
                        "url": url,
                        "status": response.status_code,
                        "saved_to": str(target),
                    }
                )
            except Exception as error:  # noqa: BLE001
                results.append(
                    {
                        "url": url,
                        "error": f"{type(error).__name__}: {error}",
                    }
                )
    return results


def main() -> int:
    args = parse_args()
    roots = [Path(root) for root in args.roots]
    candidates = iter_candidate_files(roots)

    local_hits = []
    for path in candidates:
        matches = file_matches(path)
        if matches:
            local_hits.append(
                {
                    "path": str(path),
                    "matches": matches,
                }
            )

    script_urls = extract_script_urls(roots)
    download_results: list[dict[str, Any]] | None = None
    if args.download_public_scripts and script_urls:
        download_results = maybe_download_scripts(script_urls, Path(args.scripts_cache_dir))

    report = {
        "roots": [str(root) for root in roots],
        "local_hits_count": len(local_hits),
        "local_hits": local_hits[:100],
        "script_urls_count": len(script_urls),
        "script_urls_sample": script_urls[:30],
        "download_results": download_results,
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
