from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from sandbox.sportradar_stats.run_full_stats_pipeline import (
    PipelineOptions,
    PipelineStageError,
    run_pipeline,
)
from sandbox.sportradar_stats.capture_runtime import resolve_capture_user_data_dir


class SportradarFullPipelineTests(unittest.TestCase):
    def test_resolve_capture_user_data_dir_uses_explicit_value(self) -> None:
        resolved = resolve_capture_user_data_dir("/tmp/custom-sportradar-profile")
        self.assertEqual(resolved, "/tmp/custom-sportradar-profile")

    def test_run_pipeline_auto_uses_detected_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir_name:
            out_dir = Path(tmp_dir_name)
            options = PipelineOptions(
                stats_url="https://s5.sir.sportradar.com/bet365/en/match/61624664",
                out_dir=out_dir,
            )

            async def capture_side_effect(_options: PipelineOptions) -> Path:
                self.assertEqual(_options.user_data_dir, "/tmp/chrome-sportradar-profile")
                path = out_dir / "responses.ndjson"
                path.write_text("{}\n", encoding="utf-8")
                return path

            def filter_side_effect(_options: PipelineOptions) -> dict[str, object]:
                (out_dir / "filtered_fetch.ndjson").write_text("{}\n", encoding="utf-8")
                (out_dir / "endpoints_index.json").write_text("{}", encoding="utf-8")
                return {}

            with (
                patch(
                    "sandbox.sportradar_stats.run_full_stats_pipeline.resolve_capture_user_data_dir",
                    return_value="/tmp/chrome-sportradar-profile",
                ),
                patch(
                    "sandbox.sportradar_stats.run_full_stats_pipeline.run_capture_stage",
                    new=AsyncMock(side_effect=capture_side_effect),
                ),
                patch(
                    "sandbox.sportradar_stats.run_full_stats_pipeline.run_filter_stage",
                    side_effect=filter_side_effect,
                ),
                patch(
                    "sandbox.sportradar_stats.run_full_stats_pipeline.run_analysis_stage",
                    return_value=out_dir / "endpoint_report.md",
                ),
                patch(
                    "sandbox.sportradar_stats.run_full_stats_pipeline.run_snapshot_stage",
                    return_value=out_dir / "match_snapshot.json",
                ),
                patch(
                    "sandbox.sportradar_stats.run_full_stats_pipeline.run_features_stage",
                    return_value=out_dir / "match_features.json",
                ),
            ):
                run_pipeline(options)

    def test_run_pipeline_executes_stages_in_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir_name:
            out_dir = Path(tmp_dir_name)
            options = PipelineOptions(
                stats_url="https://s5.sir.sportradar.com/bet365/en/match/61624664",
                out_dir=out_dir,
                pretty=True,
                group_json=True,
            )
            sequence: list[str] = []

            async def capture_side_effect(_options: PipelineOptions) -> Path:
                sequence.append("capture")
                path = out_dir / "responses.ndjson"
                path.write_text("{}\n", encoding="utf-8")
                return path

            def filter_side_effect(_options: PipelineOptions) -> dict[str, object]:
                sequence.append("filter")
                (out_dir / "filtered_fetch.ndjson").write_text("{}\n", encoding="utf-8")
                (out_dir / "filtered_fetch.json").write_text("[]", encoding="utf-8")
                (out_dir / "endpoints_index.json").write_text("{}", encoding="utf-8")
                return {}

            def analyze_side_effect(_options: PipelineOptions) -> Path:
                sequence.append("analyze")
                path = out_dir / "endpoint_report.md"
                path.write_text("# report\n", encoding="utf-8")
                return path

            def snapshot_side_effect(_options: PipelineOptions) -> Path:
                sequence.append("snapshot")
                path = out_dir / "match_snapshot.json"
                path.write_text("{}", encoding="utf-8")
                return path

            def features_side_effect(_options: PipelineOptions) -> Path:
                sequence.append("features")
                path = out_dir / "match_features.json"
                path.write_text("{}", encoding="utf-8")
                return path

            with (
                patch(
                    "sandbox.sportradar_stats.run_full_stats_pipeline.run_capture_stage",
                    new=AsyncMock(side_effect=capture_side_effect),
                ),
                patch(
                    "sandbox.sportradar_stats.run_full_stats_pipeline.run_filter_stage",
                    side_effect=filter_side_effect,
                ),
                patch(
                    "sandbox.sportradar_stats.run_full_stats_pipeline.run_analysis_stage",
                    side_effect=analyze_side_effect,
                ),
                patch(
                    "sandbox.sportradar_stats.run_full_stats_pipeline.run_snapshot_stage",
                    side_effect=snapshot_side_effect,
                ),
                patch(
                    "sandbox.sportradar_stats.run_full_stats_pipeline.run_features_stage",
                    side_effect=features_side_effect,
                ),
            ):
                generated_paths = run_pipeline(options)

            self.assertEqual(sequence, ["capture", "filter", "analyze", "snapshot", "features"])
            self.assertEqual(generated_paths["responses.ndjson"], out_dir / "responses.ndjson")
            self.assertEqual(generated_paths["filtered_fetch.ndjson"], out_dir / "filtered_fetch.ndjson")
            self.assertEqual(generated_paths["match_features.json"], out_dir / "match_features.json")

    def test_run_pipeline_skip_capture_starts_at_filter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir_name:
            out_dir = Path(tmp_dir_name)
            (out_dir / "responses.ndjson").write_text("{}\n", encoding="utf-8")
            options = PipelineOptions(
                stats_url="https://s5.sir.sportradar.com/bet365/en/match/61624664",
                out_dir=out_dir,
                skip_capture=True,
            )

            capture_mock = AsyncMock()

            def filter_side_effect(_options: PipelineOptions) -> dict[str, object]:
                (out_dir / "filtered_fetch.ndjson").write_text("{}\n", encoding="utf-8")
                (out_dir / "endpoints_index.json").write_text("{}", encoding="utf-8")
                return {}

            with (
                patch(
                    "sandbox.sportradar_stats.run_full_stats_pipeline.run_capture_stage",
                    new=capture_mock,
                ),
                patch(
                    "sandbox.sportradar_stats.run_full_stats_pipeline.run_filter_stage",
                    side_effect=filter_side_effect,
                ),
                patch(
                    "sandbox.sportradar_stats.run_full_stats_pipeline.run_analysis_stage",
                    return_value=out_dir / "endpoint_report.md",
                ),
                patch(
                    "sandbox.sportradar_stats.run_full_stats_pipeline.run_snapshot_stage",
                    return_value=out_dir / "match_snapshot.json",
                ),
                patch(
                    "sandbox.sportradar_stats.run_full_stats_pipeline.run_features_stage",
                    return_value=out_dir / "match_features.json",
                ),
            ):
                run_pipeline(options)

            capture_mock.assert_not_called()

    def test_run_pipeline_fails_clearly_when_filter_output_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir_name:
            out_dir = Path(tmp_dir_name)
            options = PipelineOptions(
                stats_url="https://s5.sir.sportradar.com/bet365/en/match/61624664",
                out_dir=out_dir,
                skip_capture=True,
            )
            (out_dir / "responses.ndjson").write_text("{}\n", encoding="utf-8")

            with patch(
                "sandbox.sportradar_stats.run_full_stats_pipeline.run_filter_stage",
                return_value={},
            ):
                with self.assertRaises(PipelineStageError) as exc_info:
                    run_pipeline(options)

            self.assertIn("filtered_fetch.ndjson", str(exc_info.exception))


if __name__ == "__main__":
    unittest.main()
