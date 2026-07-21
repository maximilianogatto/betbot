"""Guarda contra NameError latentes en los handlers de Telegram.

Los handlers se están partiendo por dominio (special_leagues, stats, tracking...)
moviendo definiciones entre módulos. Un nombre que queda atrás no rompe el
import: si sólo se usa adentro de un handler que ningún test ejercita, el
NameError recién aparece cuando el usuario toca ese comando o ese botón.

Fue exactamente lo que pasó con el botón "Deshacer" del auto-merge: leía
bot_data con una constante TRACKING_SERVICE_KEY que no existía en ningún lado y
el bot arrancaba igual. Este test recorre el AST y verifica que todo nombre
leído esté definido, importado o ligado en el módulo.
"""
from __future__ import annotations

import ast
import builtins
import pathlib
import unittest

HANDLERS_DIR = (
    pathlib.Path(__file__).resolve().parents[2] / "interfaces" / "telegram" / "handlers"
)


def _bound_names(tree: ast.Module) -> set[str]:
    """Nombres que el módulo define, importa o liga en cualquier ámbito.

    Es a propósito permisivo (no modela scopes): busca el nombre que no existe
    en ninguna parte, no el que se usa fuera de su ámbito.
    """

    names = set(dir(builtins))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            names.add(node.id)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                names.add((alias.asname or alias.name).split(".")[0])
        elif isinstance(node, ast.arg):
            names.add(node.arg)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            names.add(node.name)
        elif isinstance(node, ast.Global):
            names.update(node.names)
    return names


class HandlerNamesResolveTests(unittest.TestCase):
    def test_every_name_used_in_handlers_is_defined(self) -> None:
        modules = sorted(HANDLERS_DIR.glob("*.py"))
        self.assertTrue(modules, "no se encontraron módulos de handlers")

        unresolved: dict[str, list[str]] = {}
        for module in modules:
            tree = ast.parse(module.read_text(encoding="utf-8"))
            bound = _bound_names(tree)
            used = {
                node.id
                for node in ast.walk(tree)
                if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
            }
            missing = sorted(used - bound)
            if missing:
                unresolved[module.name] = missing

        self.assertEqual(
            unresolved,
            {},
            "Nombres usados pero nunca definidos ni importados (NameError en runtime). "
            "Si moviste una definición a otro módulo, importala o re-exportala.",
        )


if __name__ == "__main__":
    unittest.main()
