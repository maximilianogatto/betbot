"""Guarda contra NameError latentes en los handlers de Telegram.

Los handlers se están partiendo por dominio (special_leagues, stats, tracking...)
moviendo definiciones entre módulos. Un nombre que queda atrás no rompe el
import: si sólo se usa adentro de un handler que ningún test ejercita, el
NameError recién aparece cuando el usuario toca ese comando o ese botón.

Fue exactamente lo que pasó con el botón "Deshacer" del auto-merge: leía
bot_data con una constante TRACKING_SERVICE_KEY que no existía en ningún lado y
el bot arrancaba igual. Este test recorre el AST y verifica que todo nombre
leído esté definido, importado o ligado donde se lo lee.

El chequeo modela ÁMBITOS a propósito. La versión anterior juntaba todos los
nombres ligados en cualquier parte del módulo, así que un `from x import y`
adentro de una función hacía que `y` pareciera disponible en todo el archivo.
Ese agujero dejó pasar el NameError de `get_storage` en tracking.py: el import
vivía dentro de una función y otras ocho funciones lo usaban como si fuera de
módulo, tumbando /leagues, /league, /link_league y compañía en producción.
"""
from __future__ import annotations

import ast
import builtins
import pathlib
import unittest

HANDLERS_DIR = (
    pathlib.Path(__file__).resolve().parents[2] / "interfaces" / "telegram" / "handlers"
)

_SCOPE_NODES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


def _body_of(scope: ast.AST) -> list[ast.stmt]:
    return list(getattr(scope, "body", []))


def _local_bindings(scope: ast.AST) -> set[str]:
    """Nombres que ESTE ámbito liga, sin bajar a los ámbitos anidados.

    Es deliberadamente permisivo dentro del ámbito (las variables de una
    comprensión, que técnicamente viven en su propio scope, cuentan como
    ligadas acá): buscamos el nombre que no existe en ningún lado, no el que se
    usa un ámbito más afuera del que le corresponde.
    """

    names: set[str] = set()

    if isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef)):
        arguments = scope.args
        for argument in (
            *arguments.posonlyargs,
            *arguments.args,
            *arguments.kwonlyargs,
        ):
            names.add(argument.arg)
        if arguments.vararg:
            names.add(arguments.vararg.arg)
        if arguments.kwarg:
            names.add(arguments.kwarg.arg)

    pending = _body_of(scope)
    while pending:
        node = pending.pop()

        # Un ámbito anidado sólo aporta su nombre; su cuerpo se revisa aparte.
        if isinstance(node, _SCOPE_NODES):
            names.add(node.name)
            continue

        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                names.add((alias.asname or alias.name).split(".")[0])
            continue

        if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            names.add(node.id)
        elif isinstance(node, ast.arg):
            # Parámetros de un lambda (los de las funciones ya se tomaron arriba).
            names.add(node.arg)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            names.add(node.name)
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            names.update(node.names)
        elif isinstance(node, (ast.MatchAs, ast.MatchStar)) and node.name:
            names.add(node.name)
        elif isinstance(node, ast.MatchMapping) and node.rest:
            names.add(node.rest)

        pending.extend(ast.iter_child_nodes(node))

    return names


def _loaded_names(scope: ast.AST) -> set[str]:
    """Nombres leídos en ESTE ámbito, sin bajar a los ámbitos anidados.

    Los decoradores y los valores por defecto de una función anidada se evalúan
    en el ámbito de afuera, así que cuentan como lectura de acá.
    """

    used: set[str] = set()

    pending = _body_of(scope)
    while pending:
        node = pending.pop()

        if isinstance(node, _SCOPE_NODES):
            pending.extend(node.decorator_list)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                pending.extend(node.args.defaults)
                pending.extend(d for d in node.args.kw_defaults if d is not None)
            else:
                pending.extend(node.bases)
                pending.extend(keyword.value for keyword in node.keywords)
            continue

        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            used.add(node.id)

        pending.extend(ast.iter_child_nodes(node))

    return used


def _nested_scopes(scope: ast.AST) -> list[ast.AST]:
    found: list[ast.AST] = []
    pending = _body_of(scope)
    while pending:
        node = pending.pop()
        if isinstance(node, _SCOPE_NODES):
            found.append(node)
            continue
        pending.extend(ast.iter_child_nodes(node))
    return found


def _unresolved_in_scope(
    scope: ast.AST,
    visible_from_enclosing: set[str],
    qualified_name: str,
) -> list[tuple[str, str]]:
    """Devuelve (ámbito, nombre) por cada lectura que no resuelve."""

    visible = visible_from_enclosing | _local_bindings(scope)
    problems = [
        (qualified_name, name)
        for name in sorted(_loaded_names(scope) - visible)
    ]

    for nested in _nested_scopes(scope):
        problems.extend(
            _unresolved_in_scope(
                nested,
                visible,
                f"{qualified_name}.{nested.name}",
            )
        )

    return problems


class HandlerNamesResolveTests(unittest.TestCase):
    def test_every_name_used_in_handlers_is_defined(self) -> None:
        modules = sorted(HANDLERS_DIR.glob("*.py"))
        self.assertTrue(modules, "no se encontraron módulos de handlers")

        unresolved: dict[str, list[str]] = {}
        for module in modules:
            tree = ast.parse(module.read_text(encoding="utf-8"))
            problems = _unresolved_in_scope(tree, set(dir(builtins)), module.stem)
            if problems:
                unresolved[module.name] = [
                    f"{scope}: {name}" for scope, name in problems
                ]

        self.assertEqual(
            unresolved,
            {},
            "Nombres usados pero nunca definidos ni importados EN SU ÁMBITO "
            "(NameError en runtime). Si moviste una definición a otro módulo, "
            "importala arriba; si el import está dentro de otra función, no "
            "alcanza para el resto del módulo.",
        )

    def test_guard_detecta_import_encerrado_en_otra_funcion(self) -> None:
        """El agujero que dejó pasar el NameError de get_storage en producción.

        Un import adentro de una función NO habilita el nombre en el resto del
        módulo; si el guard no modela ámbitos, esto pasa desapercibido.
        """

        source = ast.parse(
            "def usa():\n"
            "    return get_storage()\n"
            "def importa():\n"
            "    from adapters.storage import get_storage\n"
            "    return get_storage()\n"
        )

        problems = _unresolved_in_scope(source, set(dir(builtins)), "m")

        self.assertEqual(problems, [("m.usa", "get_storage")])


if __name__ == "__main__":
    unittest.main()
