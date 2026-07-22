"""Hace ejecutable la regla de dependencias entre capas.

La migración a la arquitectura nueva sólo se sostiene si las flechas apuntan
siempre para el mismo lado: `core` no sabe de nadie, `services` no sabe de la
interfaz, `adapters` no sabe de los services ni de la interfaz. Cuando eso se
rompe el código sigue funcionando — por eso se rompe sin que nadie lo note, y
lo caro aparece después, al querer testear o reemplazar una capa.

Las violaciones que quedaban al cerrar la migración se arreglaron moviendo el
código, no agregando excepciones acá. Si este test falla, la respuesta correcta
casi siempre es mover la función, no relajar la regla.
"""
from __future__ import annotations

import ast
import pathlib
import unittest

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent

# capa -> paquetes de los que NO puede depender (ni arriba ni adentro de una función)
FORBIDDEN_IMPORTS: dict[str, tuple[str, ...]] = {
    # El dominio no depende de nada del proyecto.
    "core": ("bot", "interfaces", "adapters", "services", "extractors", "stats_providers"),
    # La lógica de negocio no conoce a Telegram ni al runtime del bot.
    "services": ("bot", "interfaces"),
    # El almacenamiento no conoce a quien lo usa.
    "adapters": ("bot", "interfaces", "services"),
    # El scheduler es neutral respecto del framework.
    "runtime": ("bot", "interfaces"),
}


def _imported_modules(tree: ast.Module) -> list[tuple[int, str]]:
    """Todos los imports del módulo, incluidos los diferidos dentro de funciones."""

    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.append((node.lineno, node.module))
        elif isinstance(node, ast.Import):
            found.extend((node.lineno, alias.name) for alias in node.names)
    return found


class LayerDependencyTests(unittest.TestCase):
    def test_layers_do_not_import_from_above(self) -> None:
        violations: list[str] = []

        for layer, banned in FORBIDDEN_IMPORTS.items():
            for path in sorted((PROJECT_ROOT / layer).rglob("*.py")):
                if "__pycache__" in path.parts:
                    continue
                tree = ast.parse(path.read_text(encoding="utf-8"))
                for lineno, module in _imported_modules(tree):
                    if module.split(".")[0] in banned:
                        rel = path.relative_to(PROJECT_ROOT)
                        violations.append(f"{rel}:{lineno} importa {module}")

        self.assertEqual(
            violations,
            [],
            "Imports que van contra la dirección de las capas. Mové el código a la "
            "capa que corresponde en vez de agregar una excepción a esta regla.",
        )


if __name__ == "__main__":
    unittest.main()
