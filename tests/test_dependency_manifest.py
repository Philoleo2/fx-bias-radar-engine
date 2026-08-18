"""Ogni dipendenza di terze parti deve essere dichiarata in un manifest.

Questo test esiste per una ragione precisa: PREWAKE ha introdotto numpy, la
prima dipendenza non-stdlib del repository. FX Bias era interamente stdlib,
quindi il workflow CI non aveva alcuno step di installazione e nessuno se n'era
accorto — il CI e' passato per anni installando zero pacchetti. Il primo import
di numpy ha rotto la build.

Il test scandisce l'AST di tutto il codice, isola gli import di terze parti e
verifica che ognuno sia dichiarato. Se qualcuno aggiunge pandas, scipy o
scikit-learn senza dichiararlo, fallisce qui invece che in CI.
"""
from __future__ import annotations

import ast
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGES = ("fx_bias_radar", "prewake", "scripts", "api", "tests")
MANIFESTS = ("requirements.txt", "requirements-prewake.txt")

# Moduli locali importati per nome semplice (script che si importano fra loro,
# helper dei test): non sono pacchetti di terze parti.
LOCAL = {"fx_bias_radar", "prewake", "api", "research", "prewake_seed"}


def _local_module_names() -> set[str]:
    names = set(LOCAL)
    for package in PACKAGES:
        directory = os.path.join(ROOT, package)
        if not os.path.isdir(directory):
            continue
        for entry in os.listdir(directory):
            if entry.endswith(".py"):
                names.add(entry[:-3])
    return names


def third_party_imports() -> dict[str, set[str]]:
    local = _local_module_names()
    stdlib = set(sys.stdlib_module_names)
    found: dict[str, set[str]] = {}
    for package in PACKAGES:
        for dirpath, _dirs, files in os.walk(os.path.join(ROOT, package)):
            if "__pycache__" in dirpath:
                continue
            for name in files:
                if not name.endswith(".py"):
                    continue
                path = os.path.join(dirpath, name)
                with open(path, "r", encoding="utf-8") as handle:
                    tree = ast.parse(handle.read(), path)
                for node in ast.walk(tree):
                    modules = []
                    if isinstance(node, ast.Import):
                        modules = [alias.name.split(".")[0] for alias in node.names]
                    elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                        modules = [node.module.split(".")[0]]
                    for module in modules:
                        if module in stdlib or module in local:
                            continue
                        found.setdefault(module, set()).add(os.path.relpath(path, ROOT))
    return found


def declared() -> set[str]:
    names = set()
    for manifest in MANIFESTS:
        path = os.path.join(ROOT, manifest)
        if not os.path.exists(path):
            continue
        for line in open(path, "r", encoding="utf-8"):
            line = line.split("#")[0].strip()
            if not line or line.startswith("-"):
                continue
            for sep in ("==", ">=", "<=", "~=", "!=", ">", "<", "["):
                line = line.split(sep)[0]
            names.add(line.strip().lower().replace("-", "_"))
    return names


class TestDependencyManifest(unittest.TestCase):
    def test_every_third_party_import_is_declared(self):
        imports = third_party_imports()
        missing = {m: sorted(p) for m, p in imports.items()
                   if m.lower().replace("-", "_") not in declared()}
        self.assertEqual(missing, {},
                         "import di terze parti non dichiarati in nessun manifest: "
                         f"{ {m: v[:3] for m, v in missing.items()} }")

    def test_numpy_is_declared(self):
        self.assertIn("numpy", declared(), "numpy e' l'unica dipendenza del runtime PREWAKE")

    def test_prewake_runtime_does_not_need_scikit_learn(self):
        """Il modello e' predict-only: sklearn serviva solo al fit della ricerca."""
        imports = third_party_imports()
        for banned in ("sklearn", "scikit_learn", "scipy", "pandas"):
            self.assertNotIn(banned, imports,
                             f"{banned} non deve entrare nel runtime di produzione")

    def test_vercel_requirements_stay_light(self):
        """requirements.txt e' cio' che Vercel installa per ogni function.

        Deve restare senza pacchetti: le function servono JSON gia' calcolati.
        Aggiungere numpy qui cambierebbe il bundle delle function FX Bias.
        """
        path = os.path.join(ROOT, "requirements.txt")
        packages = [l.split("#")[0].strip() for l in open(path, encoding="utf-8")]
        self.assertEqual([p for p in packages if p], [],
                         "requirements.txt deve restare vuoto: numpy va in requirements-prewake.txt")

    def test_ci_installs_the_manifests_before_testing(self):
        ci = open(os.path.join(ROOT, ".github", "workflows", "ci.yml"), encoding="utf-8").read()
        self.assertIn("pip install -r requirements.txt -r requirements-prewake.txt", ci)
        self.assertLess(ci.index("Install declared dependencies"), ci.index("Unit tests"))
        self.assertNotIn("continue-on-error", ci)

    def test_prewake_workflow_installs_the_manifests(self):
        wf = open(os.path.join(ROOT, ".github", "workflows", "prewake.yml"), encoding="utf-8").read()
        self.assertIn("pip install -r requirements.txt -r requirements-prewake.txt", wf)


if __name__ == "__main__":
    unittest.main()


class TestRuntimeVersionParity(unittest.TestCase):
    """Un solo runtime canonico. Il CI deve eseguire cio' che esegue produzione."""

    @staticmethod
    def _python_version(workflow: str) -> str:
        import re
        text = open(os.path.join(ROOT, ".github", "workflows", workflow), encoding="utf-8").read()
        found = re.findall(r'python-version:\s*"([^"]+)"', text)
        assert found, f"{workflow} non dichiara python-version"
        return found[0]

    def test_ci_and_prewake_workflow_share_the_python_version(self):
        ci = self._python_version("ci.yml")
        prewake = self._python_version("prewake.yml")
        self.assertEqual(ci, prewake,
                         "il CI che protegge il modello deve girare sullo stesso "
                         "Python della produzione PREWAKE")

    def test_python_version_file_matches_the_workflows(self):
        declared = open(os.path.join(ROOT, ".python-version"), encoding="utf-8").read().strip()
        self.assertEqual(declared, self._python_version("prewake.yml"))
        self.assertEqual(declared, self._python_version("ci.yml"))

    RESEARCH_PYTHON = "3.12.10"     # provenance.python della ricerca congelata

    def test_canonical_runtime_is_the_exact_frozen_research_patch(self):
        """Non basta "3.12": setup-python risolverebbe l'ultima patch.

        PAIR_PREWAKE_V1 e' frozen e in validazione prospettica: il runtime deve
        essere pinnato al patch esatto con cui la parity storica e' stata
        prodotta, e cambiarlo deve essere un atto deliberato.
        """
        for workflow in ("ci.yml", "prewake.yml"):
            version = self._python_version(workflow)
            self.assertEqual(version, self.RESEARCH_PYTHON,
                             f"{workflow} deve pinnare il patch esatto della ricerca")
            self.assertEqual(version.count("."), 2, f"{workflow}: patch mancante")

    def test_python_version_file_pins_the_same_patch(self):
        declared = open(os.path.join(ROOT, ".python-version"), encoding="utf-8").read().strip()
        self.assertEqual(declared, self.RESEARCH_PYTHON)

    def test_fx_bias_workflows_are_not_repinned(self):
        """Solo CI e PREWAKE sono allineati al runtime frozen.

        Gli altri workflow FX Bias restano su "3.12": ripinnarli sarebbe una
        modifica a FX Bias che questa PR non deve fare.
        """
        import glob
        for path in glob.glob(os.path.join(ROOT, ".github", "workflows", "*.yml")):
            name = os.path.basename(path)
            if name in ("ci.yml", "prewake.yml"):
                continue
            text = open(path, encoding="utf-8").read()
            if "python-version" in text:
                self.assertIn('python-version: "3.12"', text,
                              f"{name} non deve essere ripinnato da questa PR")

    def test_numpy_is_pinned_exactly(self):
        """Un range permetterebbe un cambio di numpy senza commit."""
        path = os.path.join(ROOT, "requirements-prewake.txt")
        lines = [l.split("#")[0].strip() for l in open(path, encoding="utf-8")]
        pins = [l for l in lines if l]
        self.assertTrue(pins, "requirements-prewake.txt non dichiara nulla")
        for pin in pins:
            self.assertIn("==", pin, f"pin non esatto: {pin}")
            self.assertNotIn(">", pin)
            self.assertNotIn("<", pin)
