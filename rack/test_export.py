"""Matrix/config regression tests; run with python3 -B -m unittest -v."""
import copy
import ast
import io
import os
from contextlib import redirect_stdout
from unittest.mock import patch
import tempfile
import unittest
from types import SimpleNamespace
from pathlib import Path

import export


class MatrixTests(unittest.TestCase):
    def test_failed_count_colors(self):
        with patch.dict(os.environ, {"FREECAD_EXPORT_COLOR": "1"}, clear=True):
            self.assertEqual(export.failed_count(0), "\033[32m0 failed\033[0m")
            self.assertEqual(export.failed_count(2), "\033[31m2 failed\033[0m")
        with patch.dict(os.environ, {"FREECAD_EXPORT_COLOR": "1", "NO_COLOR": "1"}, clear=True):
            self.assertEqual(export.failed_count(0), "0 failed")
            self.assertEqual(export.failed_count(2), "2 failed")

    def test_parallel_cli_environment_and_default_precedence(self):
        cases = [({}, [], 4), ({"PARALLEL": "8"}, [], 8),
                 ({"PARALLEL": "8"}, ["--parallel", "2"], 2),
                 ({"PARALLEL": "invalid"}, ["--paralell", "3"], 3)]
        for env, flags, expected in cases:
            with self.subTest(env=env, flags=flags), patch.dict(os.environ, env, clear=True), \
                    patch.object(export, "run_parallel", return_value=0) as run:
                self.assertEqual(export.main(["config.py", "-e", *flags]), 0)
                self.assertEqual(run.call_args.args[3], expected)

    def test_combined_tasks_pair_outputs_and_keep_cad_only_variants(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            (base / "model.FCStd").touch()
            config = dict(source_filename="model.FCStd", output_directory="cad",
                          file_extension="step", file_prefix="", exports={
                              "objects": ["clip"], "groups": [
                                  {"name": "paired"},
                                  {"name": "cad-only", "screenshot": False},
                              ]})
            path = base / "config.py"
            path.write_text("\n".join(f"{k} = {v!r}" for k, v in config.items()))
            with patch.object(export, "check_source_labels"):
                tasks = export.plan_tasks(path, True, True)
            self.assertEqual(len(tasks), 2)
            cad = next(t for t in tasks if not t["screenshot"])
            paired = next(t for t in tasks if t["screenshot"])
            self.assertEqual(cad["variant"]["filenames"], ["cad-only.step"])
            self.assertEqual(paired["variant"]["filenames"], ["paired.png"])
            self.assertEqual(paired["variant"]["cad_filenames"], ["paired.step"])
            self.assertEqual(paired["variant"]["cad_output"], str(base / "cad"))

    def test_cli_help_and_explicit_modes(self):
        with redirect_stdout(io.StringIO()) as output:
            self.assertEqual(export.main([]), 0)
        self.assertIn("--export", output.getvalue())
        for flag, screenshot in (("-e", False), ("--export", False),
                                 ("-s", True), ("--screenshot", True)):
            with self.subTest(flag=flag), patch.object(export, "run_parallel", return_value=0) as run:
                self.assertEqual(export.main([flag, "config.py"]), 0)
                run.assert_called_once_with(Path("config.py").resolve(), not screenshot, screenshot, 4, True)

    def test_cli_both_share_worker_limit(self):
        with patch.object(export, "run_parallel", return_value=1) as run:
            self.assertEqual(export.main(["-es", "config.py", "-p", "2", "--no-overwrite"]), 1)
            run.assert_called_once_with(Path("config.py").resolve(), True, True, 2, False)

    def test_config_only_lists_stl_permutations_without_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            (base / "model.FCStd").touch()
            config = dict(source_filename="model.FCStd", output_directory="out",
                          file_extension="stl", file_prefix="", exports={
                              "name": "clip", "objects": ["clip"],
                              "matrix": {"values": {"p": {"x": [1, 2]}}}})
            path = base / "config.py"
            path.write_text("\n".join(f"{k} = {v!r}" for k, v in config.items()))
            with patch.object(export, "load_freecad") as load, redirect_stdout(io.StringIO()) as output:
                self.assertEqual(export.main([str(path)]), 0)
                load.assert_not_called()
            self.assertIn("2 permutations, 2 STL files", output.getvalue())
            self.assertIn("clip-x-1.stl", output.getvalue())
            self.assertFalse((base / "out").exists())

    def test_setting_references_and_string_concatenation(self):
        settings = {"output_directory": "exports/project/"}
        expression = ast.parse('{"path": output_directory + "images/", "nested": [output_directory]}', mode="eval").body
        self.assertEqual(export.config_value(expression, settings),
                         {"path": "exports/project/images/", "nested": ["exports/project/"]})

    def test_config_expressions_reject_executable_python(self):
        for expression in ('missing', '__import__("os")', '"x".upper()',
                           '1 + 2', '[x for x in []]', '{**{}}'):
            with self.subTest(expression=expression), self.assertRaises(ValueError):
                export.config_value(ast.parse(expression, mode="eval").body, {})

    def test_independent_export_blocks(self):
        blocks = [
            {"matrix": {"values": {"p": {"x": [1, 2]}}},
             "objects": ["first"], "screenshot": True,
             "groups": [{"name": "a", "values": {"p": {"fixed": 9}}}]},
            {"matrix": {"values": {"other": {"y": [3, 4, 5]}}},
             "objects": ["second"], "groups": [{"name": "b"}]},
        ]
        before = copy.deepcopy(blocks)
        variants = list(export.expand_exports(blocks, screenshot=False))
        self.assertEqual(len(variants), 5)
        self.assertEqual(variants[0]["context"], "exports[1].groups[1]")
        self.assertEqual(variants[2]["context"], "exports[2].groups[1]")
        self.assertEqual(variants[2]["values"], {("other", "y"): 3})
        self.assertEqual(variants[2]["objects"], ["second"])
        self.assertEqual([v["screenshot"] for v in variants], [True, True, False, False, False])
        self.assertEqual(blocks, before)

    def test_export_block_validation(self):
        for value in ([], "invalid", [None]):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "exports"):
                list(export.expand_exports(value))

    def test_export_list_collisions_and_screenshot_filtering(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            (base / "model.FCStd").touch()
            config = dict(source_filename="model.FCStd", output_directory="out",
                          file_extension="step", file_prefix="", exports=[
                              {"name": "same", "objects": ["clip"]},
                              {"name": "same", "objects": ["clip"], "screenshot": False},
                          ])
            path = base / "config.py"
            path.write_text("\n".join(f"{k} = {v!r}" for k, v in config.items()))
            with self.assertRaisesRegex(ValueError, "Filename collision"):
                export.read_config(path)
            parsed, _, _, variants = export.read_config(path, screenshot=True)
            self.assertEqual(len(variants), 1)
            self.assertEqual(parsed["skipped_screenshots"], 1)

    def test_global_screenshot_default_and_group_overrides(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            (base / "model.FCStd").touch()
            config = dict(source_filename="model.FCStd", output_directory="out",
                          file_extension="step", file_prefix="",
                          screenshots={"screenshot": False},
                          exports={"objects": ["clip"], "groups": [
                              {"name": "inherited"},
                              {"name": "enabled", "screenshot": True},
                              {"name": "disabled", "screenshot": False},
                          ]})
            path = base / "config.py"
            for default, expected in ((False, ["enabled"]),
                                      (True, ["inherited", "enabled"])):
                config["screenshots"]["screenshot"] = default
                path.write_text("\n".join(f"{key} = {value!r}" for key, value in config.items()))
                variants = export.read_config(path, screenshot=True)[3]
                self.assertEqual([v["name"] for v in variants], expected)
                self.assertEqual(len(export.read_config(path)[3]), 3)

    def test_screenshot_group_inheritance(self):
        group = {"name": "clip", "objects": ["clip"], "groups": [
            {}, {"screenshot": False, "groups": [{}, {"screenshot": True}]},
        ]}
        self.assertEqual([v["screenshot"] for v in export.expand_groups(group)],
                         [True, False, True])
        group["screenshot"] = "false"
        with self.assertRaisesRegex(ValueError, "screenshot must be"):
            list(export.expand_groups(group))

    def test_suppressed_screenshots_do_not_affect_cad(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            (base / "model.FCStd").touch()
            config = dict(source_filename="model.FCStd", output_directory="out",
                          file_extension="step", file_prefix="",
                          exports={"name": "clip", "objects": ["clip"], "screenshot": False})
            path = base / "config.py"
            path.write_text("\n".join(f"{key} = {value!r}" for key, value in config.items()))
            self.assertEqual(len(export.read_config(path)[3]), 1)
            parsed, _, _, variants = export.read_config(path, screenshot=True)
            self.assertEqual(variants, [])
            self.assertEqual(parsed["skipped_screenshots"], 1)
            export.run(path, screenshot=True)  # No CAD loading or GUI startup.

    def test_failure_summary_identifies_values_outputs_and_stage(self):
        variant = {"context": "exports.groups[1]", "objects": ["clip", "other"],
                   "filenames": ["clip-slots-2.png", "other-slots-2.png"],
                   "values": {("parameters", "slots"): 2,
                              ("parameters", "slot_width"): "2.5 mm"}}
        report = export.failure_details(1, variant, Path("/tmp/images"),
                                        "validating shape of 'clip'", ValueError("invalid geometry"),
                                        {"other-slots-2.png"})
        for text in ("exports.groups[1]", "validating shape", "ValueError: invalid geometry",
                     "parameters.slots = 2", "parameters.slot_width = '2.5 mm'",
                     "/tmp/images/clip-slots-2.png [not written this run]",
                     "/tmp/images/other-slots-2.png [published]"):
            self.assertIn(text, report)

    def test_shape_error_distinguishes_empty_and_invalid(self):
        obj = SimpleNamespace(Label="clip", Name="Body")
        with self.assertRaisesRegex(ValueError, "no Shape property"):
            export.validate_shape(obj)
        obj.Shape = SimpleNamespace(isNull=lambda: True)
        with self.assertRaisesRegex(ValueError, "empty/null"):
            export.validate_shape(obj)
        obj.Shape = SimpleNamespace(isNull=lambda: False, isValid=lambda: False,
                                    Solids=[1], Shells=[1], Faces=[1, 2])
        obj.getStatusString = lambda: "Up-to-date"
        obj.Tip = SimpleNamespace(Label="Fillet", Name="Fillet001")
        with self.assertRaisesRegex(ValueError, "1 solids, 1 shells, 2 faces.*Fillet001"):
            export.validate_shape(obj)

    def setUp(self):
        self.group = {
            "name": "{object}-{parameters.x}-{mounting.y}",
            "objects": ["clip"],
            "matrix": {"values": {
                "parameters": {"x": [1, 2]},
                "mounting": {"y": [3, 4]},
            }},
        }

    def test_cross_product_across_varsets(self):
        variants = list(export.expand_groups(self.group))
        self.assertEqual({(v["values"]["parameters", "x"], v["values"]["mounting", "y"])
                          for v in variants}, {(1, 3), (1, 4), (2, 3), (2, 4)})

    def test_nested_overrides_before_expansion_and_sibling_isolation(self):
        self.group["groups"] = [
            {"values": {"parameters": {"x": 9}}, "groups": [
                {"matrix": {"values": {"mounting": {"y": [8]}}}},
            ]},
            {},
        ]
        before = copy.deepcopy(self.group)
        variants = list(export.expand_groups(self.group))
        self.assertEqual(len(variants), 5)
        self.assertEqual(variants[0]["values"], {("parameters", "x"): 9, ("mounting", "y"): 8})
        self.assertEqual(variants[0]["matrix_keys"], [("mounting", "y")])
        self.assertEqual(variants[1]["matrix_keys"], [("mounting", "y"), ("parameters", "x")])
        self.assertEqual(self.group, before)

    def test_inner_matrix_replaces_fixed_value_and_objects(self):
        group = {"name": "{object}-{p.x}", "objects": ["outer"],
                 "values": {"p": {"x": 1}}, "groups": [
                     {"objects": ["inner"], "matrix": {"values": {"p": {"x": [2, 3]}}}},
                 ]}
        variants = list(export.expand_groups(group))
        self.assertEqual([v["values"]["p", "x"] for v in variants], [2, 3])
        self.assertTrue(all(v["objects"] == ["inner"] for v in variants))
        self.assertTrue(all(v["matrix_keys"] == [("p", "x")] for v in variants))

    def test_automatic_matrix_suffix(self):
        group = {"name": "{object}-1.4x6.1", "objects": ["clip"],
                 "values": {"parameters": {"slot_width": "1.4 mm"}},
                 "matrix": {"values": {"parameters": {
                     "slot_separation": ["0 mm", "1 mm"],
                     "length": ["10 mm", "15 mm"],
                 }}}}
        names = [export.filename("", v["name"], "clip", v["values"], "step", v["matrix_keys"])
                 for v in export.expand_groups(group)]
        self.assertEqual(set(names), {
            f"clip-1.4x6.1-length-{length}mm_slot_separation-{spacing}mm.step"
            for length in (10, 15) for spacing in (0, 1)})

    def test_duplicate_axis_names_are_qualified(self):
        values = {("b", "size"): 2, ("a", "size"): 1, ("a", "length"): 3}
        self.assertEqual(export.filename("", "clip", "clip", values, "png", values),
                         "clip-length-3_a.size-1_b.size-2.png")

    def test_conflicting_definitions(self):
        self.group["values"] = {"parameters": {"x": 5}}
        with self.assertRaisesRegex(ValueError, "both values and matrix"):
            list(export.expand_groups(self.group))

    def test_empty_axis_rejected(self):
        self.group["matrix"]["values"]["parameters"]["x"] = []
        with self.assertRaisesRegex(ValueError, "nonempty candidate list"):
            list(export.expand_groups(self.group))

    def test_empty_overrides_and_template(self):
        variants = list(export.expand_groups({"name": "plain", "objects": ["clip"]}))
        self.assertEqual(len(variants), 1)
        self.assertEqual(variants[0]["values"], {})
        self.assertEqual(export.filename("foo_", "{object}-{p.x}", "clip", {("p", "x"): "1 mm"}, "step"),
                         "foo_clip-1mm.step")
        self.assertEqual(export.filename("", "{p.angle}", "clip", {("p", "angle"): "130 °"}, "step"),
                         "130deg.step")
        with self.assertRaisesRegex(ValueError, "Unknown name template field"):
            export.filename("", "{p.missing}", "clip", {}, "step")

    def test_collision_after_sanitization(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            (base / "model.FCStd").touch()
            config = dict(source_filename="model.FCStd", output_directory="out",
                          file_extension="step", file_prefix="", exports={
                              "name": "{p.x}", "objects": ["clip"],
                              "matrix": {"values": {"p": {"x": ["a b", "a/b"]}}},
                          })
            path = base / "config.py"
            path.write_text("\n".join(f"{key} = {value!r}" for key, value in config.items()))
            with self.assertRaisesRegex(ValueError, "Filename collision"):
                export.read_config(path)

    def test_screenshot_checks_png_collisions_independently(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            (base / "model.FCStd").touch()
            (base / "out").mkdir()
            (base / "out/clip.step").touch()
            config = dict(source_filename="model.FCStd", output_directory="out",
                          file_extension="step", file_prefix="",
                          screenshots={"output_directory": "out"},
                          exports={"name": "clip", "objects": ["clip"]})
            path = base / "config.py"
            path.write_text("\n".join(f"{key} = {value!r}" for key, value in config.items()))
            _, _, _, variants = export.read_config(path, screenshot=True)
            self.assertEqual(variants[0]["filenames"], ["clip.png"])
            export.read_config(path)  # Existing CAD output is allowed by default.
            with self.assertRaisesRegex(ValueError, "Output already exists"):
                export.read_config(path, overwrite=False)
            (base / "out/clip.png").touch()
            export.read_config(path, screenshot=True)
            with self.assertRaisesRegex(ValueError, "Output already exists"):
                export.read_config(path, screenshot=True, overwrite=False)

    def test_screenshot_settings_and_relative_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            (base / "model.FCStd").touch()
            config = dict(source_filename="model.FCStd", output_directory="cad",
                          file_extension="step", file_prefix="",
                          screenshots={"output_directory": "previews", "width": 800,
                                       "height": 600, "background": "#505050"},
                          exports={"name": "clip", "objects": ["clip"]})
            path = base / "config.py"

            def write():
                path.write_text("\n".join(f"{key} = {value!r}" for key, value in config.items()))

            write()
            parsed, _, output, _ = export.read_config(path, screenshot=True)
            self.assertEqual(output, base / "previews")
            self.assertEqual(parsed["screenshots"], {"screenshot": True, **config["screenshots"]})
            self.assertEqual(export.read_config(path)[2], base / "cad")
            for key, value in (("width", True), ("height", 0), ("background", "invalid"),
                               ("output_directory", "")):
                with self.subTest(key=key):
                    previous = config["screenshots"][key]
                    config["screenshots"][key] = value
                    write()
                    with self.assertRaisesRegex(ValueError, "screenshots"):
                        export.read_config(path, screenshot=True)
                    config["screenshots"][key] = previous


if __name__ == "__main__":
    unittest.main()
