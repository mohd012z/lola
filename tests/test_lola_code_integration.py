from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import lola_code_integration as integration


class LolaCodeIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def write(self, name: str, content: str) -> Path:
        path = self.root / name
        path.write_text(content, encoding="utf-8")
        return path

    def test_identify_supports_cpp_node_and_vbscript_extensions(self) -> None:
        cpp = self.write("demo.cxx", "int main() { return 0; }\n")
        js = self.write("demo.mjs", "export const x = 1;\n")
        vbs = self.write("demo.wsf", "<job><script language='VBScript'></script></job>\n")

        self.assertEqual(integration.identify(cpp)["language"], "cpp")
        self.assertEqual(integration.identify(js)["language"], "javascript")
        self.assertEqual(integration.identify(vbs)["language"], "vbscript")

    def test_cpp_compile_plan_detects_multiple_compilers(self) -> None:
        cpp = self.write("demo.hpp", "#pragma once\n")

        with patch.object(
            integration,
            "runtime_inventory",
            return_value={
                "python": [],
                "javascript": [],
                "typescript": [],
                "java": [],
                "kotlin": [],
                "c": [],
                "cpp": [
                    {"tool": "g++", "path": "/usr/bin/g++"},
                    {"tool": "clang++", "path": "/usr/bin/clang++"},
                    {"tool": "cl.exe", "path": "C:/VS/cl.exe"},
                ],
                "csharp": [],
                "vbscript": [],
                "shell": [],
                "powershell": [],
                "mql4": [],
                "mql5": [],
                "smali": [],
            },
        ):
            plan = integration.compile_plan(cpp)

        self.assertTrue(plan["supported"])
        routes = " ".join(plan["routes"])
        self.assertIn("g++ -fsyntax-only", routes)
        self.assertIn("clang++ -fsyntax-only", routes)
        self.assertIn("cl /Zs", routes)

    def test_node_compile_plan_uses_node_check(self) -> None:
        js = self.write("demo.cjs", "module.exports = 1;\n")

        with patch.object(
            integration,
            "runtime_inventory",
            return_value={
                "python": [],
                "javascript": [{"tool": "node", "path": "/usr/bin/node"}],
                "typescript": [],
                "java": [],
                "kotlin": [],
                "c": [],
                "cpp": [],
                "csharp": [],
                "vbscript": [],
                "shell": [],
                "powershell": [],
                "mql4": [],
                "mql5": [],
                "smali": [],
            },
        ):
            plan = integration.compile_plan(js)

        self.assertTrue(plan["supported"])
        self.assertEqual(plan["routes"], ["node --check <file>"])

    def test_vbscript_is_windows_only(self) -> None:
        script = self.write("demo.vbs", "WScript.Echo \"hi\"\n")

        with patch("platform.system", return_value="Linux"):
            plan = integration.compile_plan(script)

        self.assertFalse(plan["supported"])
        self.assertTrue(plan["windowsOnly"])


if __name__ == "__main__":
    unittest.main()
