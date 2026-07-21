"""Contrato estático entre los consumidores del storage y el facade.

Los tests de cada adapter se corren aislados, así que NO cazan el desajuste entre
lo que services/handlers *llaman* y lo que el facade *acepta*. Ese hueco tumbó el
job de tracking en producción durante 9 días:

    TypeError: SQLiteSubscriptionsAdapter.get_subscriptions_for_competition()
               got an unexpected keyword argument 'only_enabled'

El bot seguía "activo" y refrescando, pero el job moría al notificar → cero alertas.
Antes hubo la misma clase de fallo con `only_future` (x2) y con los parámetros de
`update_tracked_competition_source`.

Estos tests recorren el AST del código real y verifican que todo lo que se le pide
al storage exista y acepte esos kwargs.
"""
from __future__ import annotations

import ast
import inspect
import unittest
from pathlib import Path

from adapters.storage import SqliteStorage

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SCANNED_PACKAGES = ("bot", "monitors", "core")
# Receivers que representan al storage en el código.
STORAGE_RECEIVERS = {
    "repository", "tracking_repository", "storage", "_repository", "_storage", "_cache",
}


def _facade_signatures() -> dict[str, inspect.Signature]:
    sigs: dict[str, inspect.Signature] = {}
    for name in dir(SqliteStorage):
        if name.startswith("_"):
            continue
        member = getattr(SqliteStorage, name)
        if callable(member):
            try:
                sigs[name] = inspect.signature(member)
            except (ValueError, TypeError):
                pass
    return sigs


def _accepts(signature: inspect.Signature, keyword: str) -> bool:
    params = signature.parameters
    if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()):
        return True
    return keyword in params


def _iter_python_files():
    for package in SCANNED_PACKAGES:
        root = PROJECT_ROOT / package
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            if "__pycache__" in str(path):
                continue
            yield path


class StorageCallContractTests(unittest.TestCase):
    def test_kwargs_passed_to_storage_are_accepted_by_the_facade(self) -> None:
        signatures = _facade_signatures()
        self.assertGreater(len(signatures), 50, "El facade debería exponer los ports de storage")

        problems: list[str] = []
        for path in _iter_python_files():
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except SyntaxError:  # pragma: no cover
                continue
            for node in ast.walk(tree):
                if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
                    continue
                method = node.func.attr
                signature = signatures.get(method)
                if signature is None:
                    continue
                for keyword in node.keywords:
                    if keyword.arg is None:
                        continue
                    if not _accepts(signature, keyword.arg):
                        rel = path.relative_to(PROJECT_ROOT)
                        problems.append(
                            f"{rel}:{node.lineno} → {method}(..., {keyword.arg}=...) "
                            f"pero el facade acepta {tuple(signature.parameters)}"
                        )

        self.assertEqual(
            sorted(set(problems)),
            [],
            "Hay llamadas al storage con kwargs que el facade no acepta "
            "(TypeError en runtime):\n  " + "\n  ".join(sorted(set(problems))),
        )

    def test_methods_requested_from_storage_exist_in_the_facade(self) -> None:
        available = {name for name in dir(SqliteStorage) if not name.startswith("_")}

        def is_storage_receiver(value: ast.AST) -> bool:
            if isinstance(value, ast.Name):
                return value.id in STORAGE_RECEIVERS
            if isinstance(value, ast.Attribute):
                return value.attr in STORAGE_RECEIVERS
            if isinstance(value, ast.Call) and isinstance(value.func, ast.Name):
                return value.func.id == "get_storage"
            return False

        problems: list[str] = []
        for path in _iter_python_files():
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except SyntaxError:  # pragma: no cover
                continue
            for node in ast.walk(tree):
                # Cubre tanto la llamada directa como pasar el método como valor
                # (p.ej. asyncio.to_thread(repo.metodo, ...)).
                if not (isinstance(node, ast.Attribute) and is_storage_receiver(node.value)):
                    continue
                if node.attr.startswith("_") or node.attr in available:
                    continue
                problems.append(f"{path.relative_to(PROJECT_ROOT)}:{node.lineno} → {node.attr}")

        self.assertEqual(
            sorted(set(problems)),
            [],
            "Se le piden al storage métodos que el facade no tiene "
            "(AttributeError en runtime):\n  " + "\n  ".join(sorted(set(problems))),
        )


if __name__ == "__main__":
    unittest.main()
