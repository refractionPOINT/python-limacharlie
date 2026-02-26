"""Tests for the dr convert-rules command and supporting classes."""

import json
import os
import textwrap
from unittest.mock import MagicMock, patch, call

import pytest

from limacharlie.commands._dr_convert import (
    ConversionPipeline,
    ConversionResult,
    GitHubCrawler,
    LocalCrawler,
    ProgressDisplay,
    RuleFile,
    is_rule_file,
    _has_rule_dir_ancestor,
)


# ---------------------------------------------------------------------------
# is_rule_file
# ---------------------------------------------------------------------------

class TestIsRuleFile:
    def test_yaml_accepted(self):
        assert is_rule_file("rules/my_rule.yml") is True
        assert is_rule_file("detections/proc.yaml") is True

    def test_json_accepted(self):
        assert is_rule_file("searches/query.json") is True

    def test_sigma_accepted(self):
        assert is_rule_file("rules/sigma_rule.sigma") is True

    def test_spl_accepted(self):
        assert is_rule_file("rules/splunk_search.spl") is True

    def test_kql_accepted(self):
        assert is_rule_file("rules/azure.kql") is True

    def test_toml_accepted(self):
        assert is_rule_file("rules/elastic_rule.toml") is True

    def test_readme_rejected(self):
        assert is_rule_file("rules/README.md") is False

    def test_license_rejected(self):
        assert is_rule_file("LICENSE") is False

    def test_gitignore_rejected(self):
        assert is_rule_file(".gitignore") is False

    def test_requirements_rejected(self):
        assert is_rule_file("requirements.txt") is False

    def test_pyproject_rejected(self):
        assert is_rule_file("pyproject.toml") is False

    def test_docker_compose_rejected(self):
        assert is_rule_file("docker-compose.yml") is False

    def test_github_dir_rejected(self):
        assert is_rule_file(".github/workflows/ci.yml") is False

    def test_tests_dir_rejected(self):
        assert is_rule_file("tests/test_rule.yaml") is False

    def test_docs_dir_rejected(self):
        assert is_rule_file("docs/examples/rule.yaml") is False

    def test_txt_extension_rejected(self):
        assert is_rule_file("notes.txt") is False

    def test_py_extension_rejected(self):
        assert is_rule_file("convert.py") is False

    def test_nested_rule_file(self):
        assert is_rule_file("rules/windows/process_creation/mimikatz.yml") is True

    def test_pre_commit_config_rejected(self):
        assert is_rule_file(".pre-commit-config.yaml") is False

    def test_mkdocs_rejected(self):
        assert is_rule_file("mkdocs.yml") is False

    def test_yamllint_rejected(self):
        assert is_rule_file(".yamllint.yml") is False


class TestHasRuleDirAncestor:
    def test_rules_dir(self):
        assert _has_rule_dir_ancestor("rules/my_rule.yml") is True

    def test_detections_dir(self):
        assert _has_rule_dir_ancestor("detections/proc.yaml") is True

    def test_sigma_dir(self):
        assert _has_rule_dir_ancestor("sigma/windows/rule.yml") is True

    def test_no_rule_dir(self):
        assert _has_rule_dir_ancestor("misc/something.yml") is False

    def test_file_at_root(self):
        assert _has_rule_dir_ancestor("rule.yml") is False

    def test_nested_rule_dir(self):
        assert _has_rule_dir_ancestor("project/rules/windows/rule.yml") is True


# ---------------------------------------------------------------------------
# GitHubCrawler URL parsing
# ---------------------------------------------------------------------------

class TestGitHubCrawlerParseRepo:
    def test_short_form(self):
        owner, repo = GitHubCrawler._parse_repo("SigmaHQ/sigma")
        assert owner == "SigmaHQ"
        assert repo == "sigma"

    def test_https_url(self):
        owner, repo = GitHubCrawler._parse_repo("https://github.com/SigmaHQ/sigma")
        assert owner == "SigmaHQ"
        assert repo == "sigma"

    def test_https_url_with_git(self):
        owner, repo = GitHubCrawler._parse_repo("https://github.com/elastic/detection-rules.git")
        assert owner == "elastic"
        assert repo == "detection-rules"

    def test_http_url(self):
        owner, repo = GitHubCrawler._parse_repo("http://github.com/owner/repo")
        assert owner == "owner"
        assert repo == "repo"

    def test_bare_domain(self):
        owner, repo = GitHubCrawler._parse_repo("github.com/owner/repo")
        assert owner == "owner"
        assert repo == "repo"

    def test_trailing_slash(self):
        owner, repo = GitHubCrawler._parse_repo("SigmaHQ/sigma/")
        assert owner == "SigmaHQ"
        assert repo == "sigma"

    def test_invalid_raises(self):
        with pytest.raises(ValueError, match="Cannot parse"):
            GitHubCrawler._parse_repo("just-a-name")

    def test_url_with_extra_path(self):
        owner, repo = GitHubCrawler._parse_repo("https://github.com/owner/repo/tree/main/rules")
        assert owner == "owner"
        assert repo == "repo"


class TestGitHubCrawlerDisplayName:
    def test_basic(self):
        crawler = GitHubCrawler.__new__(GitHubCrawler)
        crawler._owner = "SigmaHQ"
        crawler._repo = "sigma"
        crawler._path = None
        crawler._ref = None
        assert crawler.display_name == "SigmaHQ/sigma"

    def test_with_path_and_ref(self):
        crawler = GitHubCrawler.__new__(GitHubCrawler)
        crawler._owner = "SigmaHQ"
        crawler._repo = "sigma"
        crawler._path = "rules/windows"
        crawler._ref = "main"
        assert crawler.display_name == "SigmaHQ/sigma/rules/windows @ main"


# ---------------------------------------------------------------------------
# LocalCrawler
# ---------------------------------------------------------------------------

class TestLocalCrawler:
    def test_finds_yaml_files(self, tmp_path):
        (tmp_path / "rule1.yml").write_text("title: rule1")
        (tmp_path / "rule2.yaml").write_text("title: rule2")
        (tmp_path / "README.md").write_text("# readme")

        results = LocalCrawler(str(tmp_path)).crawl()
        filenames = {r.filename for r in results}
        assert "rule1.yml" in filenames
        assert "rule2.yaml" in filenames
        assert "README.md" not in filenames

    def test_skips_hidden_files(self, tmp_path):
        (tmp_path / ".hidden.yml").write_text("title: hidden")
        (tmp_path / "visible.yml").write_text("title: visible")

        results = LocalCrawler(str(tmp_path)).crawl()
        filenames = {r.filename for r in results}
        assert ".hidden.yml" not in filenames
        assert "visible.yml" in filenames

    def test_skips_hidden_dirs(self, tmp_path):
        hidden = tmp_path / ".git"
        hidden.mkdir()
        (hidden / "config.yml").write_text("something")
        (tmp_path / "rule.yml").write_text("title: rule")

        results = LocalCrawler(str(tmp_path)).crawl()
        assert len(results) == 1
        assert results[0].filename == "rule.yml"

    def test_skips_empty_files(self, tmp_path):
        (tmp_path / "empty.yml").write_text("")
        (tmp_path / "whitespace.yml").write_text("   \n  ")
        (tmp_path / "real.yml").write_text("title: real")

        results = LocalCrawler(str(tmp_path)).crawl()
        assert len(results) == 1
        assert results[0].filename == "real.yml"

    def test_recursive(self, tmp_path):
        sub = tmp_path / "rules" / "windows"
        sub.mkdir(parents=True)
        (sub / "proc.yml").write_text("title: proc")
        (tmp_path / "root.yaml").write_text("title: root")

        results = LocalCrawler(str(tmp_path)).crawl()
        filenames = {r.filename for r in results}
        assert "proc.yml" in filenames
        assert "root.yaml" in filenames

    def test_skips_test_dirs(self, tmp_path):
        tests = tmp_path / "tests"
        tests.mkdir()
        (tests / "test_rule.yml").write_text("title: test")
        (tmp_path / "rule.yml").write_text("title: rule")

        results = LocalCrawler(str(tmp_path)).crawl()
        assert len(results) == 1


# ---------------------------------------------------------------------------
# ConversionPipeline
# ---------------------------------------------------------------------------

class TestConversionPipelineSanitizeKey:
    def _make_pipeline(self):
        org = MagicMock()
        return ConversionPipeline(org, prefix="")

    def test_basic(self):
        p = self._make_pipeline()
        assert p._sanitize_key("My Cool Rule.yml") == "my-cool-rule"

    def test_special_chars(self):
        p = self._make_pipeline()
        assert p._sanitize_key("rule (v2) [final].yaml") == "rule-v2-final"

    def test_with_prefix(self):
        org = MagicMock()
        p = ConversionPipeline(org, prefix="sigma")
        assert p._sanitize_key("mimikatz.yml") == "sigma-mimikatz"

    def test_empty_name(self):
        p = self._make_pipeline()
        assert p._sanitize_key("!!!.yml") == "rule"

    def test_preserves_numbers(self):
        p = self._make_pipeline()
        assert p._sanitize_key("rule_123_v2.yml") == "rule-123-v2"

    def test_prefix_sanitized(self):
        """Prefix with special chars gets sanitized to safe hive key."""
        org = MagicMock()
        p = ConversionPipeline(org, prefix="My Prefix!!")
        assert p._sanitize_key("rule.yml") == "my-prefix-rule"

    def test_prefix_path_traversal_sanitized(self):
        """Prefix containing path traversal components gets sanitized."""
        org = MagicMock()
        p = ConversionPipeline(org, prefix="../../etc")
        assert p._sanitize_key("rule.yml") == "etc-rule"


class TestConversionPipelineUniqueKey:
    def test_first_call_no_suffix(self):
        org = MagicMock()
        p = ConversionPipeline(org)
        assert p._unique_key("rule.yml") == "rule"

    def test_duplicate_gets_suffix(self):
        org = MagicMock()
        p = ConversionPipeline(org)
        assert p._unique_key("rule.yml") == "rule"
        assert p._unique_key("rule.yml") == "rule-2"
        assert p._unique_key("rule.yml") == "rule-3"

    def test_different_names_no_collision(self):
        org = MagicMock()
        p = ConversionPipeline(org)
        assert p._unique_key("alpha.yml") == "alpha"
        assert p._unique_key("beta.yml") == "beta"


class TestConversionPipelineParseResponse:
    def test_extracts_response_key(self):
        resp = {"response": {"event": "NEW_PROCESS"}}
        assert ConversionPipeline._parse_ai_response(resp) == {"event": "NEW_PROCESS"}

    def test_extracts_detection_key(self):
        resp = {"detection": {"op": "is"}}
        assert ConversionPipeline._parse_ai_response(resp) == {"op": "is"}

    def test_returns_raw_if_no_known_key(self):
        resp = {"something": "else"}
        assert ConversionPipeline._parse_ai_response(resp) == resp

    def test_returns_non_dict_as_is(self):
        assert ConversionPipeline._parse_ai_response("raw string") == "raw string"


class TestConversionPipelineConvertOne:
    def test_success(self):
        org = MagicMock()
        p = ConversionPipeline(org)

        detect_data = {"event": "NEW_PROCESS", "op": "contains", "path": "event/COMMAND_LINE", "value": "mimikatz"}
        respond_data = [{"action": "report", "name": "mimikatz-detected"}]

        p._ai = MagicMock()
        p._ai.generate_detection.return_value = {"response": detect_data}
        p._ai.generate_response.return_value = {"response": respond_data}

        rf = RuleFile(path="rules/mimikatz.yml", content="title: Mimikatz", filename="mimikatz.yml")
        result = p._convert_one(rf)

        assert result.success is True
        assert result.detect == detect_data
        assert result.respond == respond_data
        assert p._ai.generate_detection.called
        assert p._ai.generate_response.called

    def test_detection_failure(self):
        org = MagicMock()
        p = ConversionPipeline(org)

        p._ai = MagicMock()
        p._ai.generate_detection.side_effect = Exception("AI error")

        rf = RuleFile(path="rules/bad.yml", content="garbage", filename="bad.yml")
        result = p._convert_one(rf)

        assert result.success is False
        assert "AI error" in result.error

    def test_response_failure(self):
        org = MagicMock()
        p = ConversionPipeline(org)

        p._ai = MagicMock()
        p._ai.generate_detection.return_value = {"response": {"event": "X"}}
        p._ai.generate_response.side_effect = Exception("Response error")

        rf = RuleFile(path="rules/partial.yml", content="title: Partial", filename="partial.yml")
        result = p._convert_one(rf)

        assert result.success is False
        assert "Response error" in result.error

    def test_non_dict_detect_fails(self):
        """AI returning a non-dict detect (e.g. None from yaml parse) is a failure."""
        org = MagicMock()
        p = ConversionPipeline(org)

        p._ai = MagicMock()
        # Return a string that yaml.safe_load turns into None
        p._ai.generate_detection.return_value = {"response": "null"}
        p._ai.generate_response.return_value = {"response": [{"action": "report", "name": "x"}]}

        rf = RuleFile(path="rules/bad.yml", content="title: Bad", filename="bad.yml")
        result = p._convert_one(rf)

        assert result.success is False
        assert "non-dict" in result.error


class TestConversionPipelineConvertAll:
    def test_parallel_execution(self):
        org = MagicMock()
        p = ConversionPipeline(org, parallel=2)

        p._ai = MagicMock()
        p._ai.generate_detection.return_value = {"response": {"event": "X"}}
        p._ai.generate_response.return_value = {"response": [{"action": "report", "name": "x"}]}

        rule_files = [
            RuleFile(path=f"r{i}.yml", content=f"rule {i}", filename=f"r{i}.yml")
            for i in range(5)
        ]

        results = p.convert_all(rule_files)
        assert len(results) == 5
        assert all(r.success for r in results)

    def test_mixed_success_and_failure(self):
        org = MagicMock()
        p = ConversionPipeline(org, parallel=1)

        call_count = 0
        def mock_detect(query):
            nonlocal call_count
            call_count += 1
            if call_count % 2 == 0:
                raise Exception("fail")
            return {"response": {"event": "X"}}

        p._ai = MagicMock()
        p._ai.generate_detection.side_effect = mock_detect
        p._ai.generate_response.return_value = {"response": [{"action": "report", "name": "x"}]}

        rule_files = [
            RuleFile(path=f"r{i}.yml", content=f"rule {i}", filename=f"r{i}.yml")
            for i in range(4)
        ]

        results = p.convert_all(rule_files)
        succeeded = [r for r in results if r.success]
        failed = [r for r in results if not r.success]
        assert len(succeeded) == 2
        assert len(failed) == 2

    def test_progress_callback_called(self):
        org = MagicMock()
        p = ConversionPipeline(org, parallel=1)

        p._ai = MagicMock()
        p._ai.generate_detection.return_value = {"response": {"event": "X"}}
        p._ai.generate_response.return_value = {"response": [{"action": "report", "name": "x"}]}

        calls = []
        def cb(completed, total, failed, current):
            calls.append((completed, total, failed))

        rule_files = [RuleFile(path="r.yml", content="rule", filename="r.yml")]
        p.convert_all(rule_files, progress_callback=cb)

        assert len(calls) == 1
        assert calls[0] == (1, 1, 0)


# ---------------------------------------------------------------------------
# ProgressDisplay
# ---------------------------------------------------------------------------

class TestProgressDisplay:
    def test_quiet_mode_no_output(self, capsys):
        pd = ProgressDisplay(10, quiet=True)
        pd.update(5, 10, 1, "file.yml")
        pd.finish([])
        out = capsys.readouterr()
        assert out.out == ""

    def test_fmt_duration_seconds(self):
        assert ProgressDisplay._fmt_duration(45) == "45s"

    def test_fmt_duration_minutes(self):
        assert ProgressDisplay._fmt_duration(125) == "2m 5s"

    def test_fmt_duration_hours(self):
        assert ProgressDisplay._fmt_duration(3665) == "1h 1m"

    def test_finish_shows_summary(self, capsys):
        pd = ProgressDisplay(2, quiet=False)
        results = [
            ConversionResult("a.yml", "a", True, {"event": "X"}, [{"action": "report"}], created_in_hive=True),
            ConversionResult("b.yml", "b", False, error="boom"),
        ]
        pd.finish(results)
        out = capsys.readouterr().out
        assert "Total rules:" in out
        assert "Converted:" in out
        assert "Failed:" in out

    def test_finish_shows_failed_rules(self, capsys):
        pd = ProgressDisplay(1, quiet=False)
        results = [
            ConversionResult("bad.yml", "bad", False, error="AI timeout"),
        ]
        pd.finish(results)
        combined = capsys.readouterr()
        assert "bad.yml" in combined.err
        assert "AI timeout" in combined.err


# ---------------------------------------------------------------------------
# CLI integration (Click CliRunner)
# ---------------------------------------------------------------------------

class TestConvertRulesCommand:
    def _invoke(self, args, **kwargs):
        from click.testing import CliRunner
        from limacharlie.cli import cli
        return CliRunner().invoke(cli, ["dr", "convert-rules"] + args, catch_exceptions=False, **kwargs)

    def test_help(self):
        result = self._invoke(["--help"])
        assert result.exit_code == 0
        assert "Mass-convert" in result.output
        assert "--github" in result.output
        assert "--input-dir" in result.output

    def test_no_input_source_error(self):
        from click.testing import CliRunner
        from limacharlie.cli import cli
        result = CliRunner().invoke(cli, ["dr", "convert-rules"])
        assert result.exit_code != 0
        assert "Provide --input-dir or --github" in result.output

    def test_both_input_sources_error(self):
        from click.testing import CliRunner
        from limacharlie.cli import cli
        result = CliRunner().invoke(cli, ["dr", "convert-rules", "--input-dir", "/tmp", "--github", "owner/repo"])
        assert result.exit_code != 0
        assert "not both" in result.output

    def test_dry_run_local_dir(self, tmp_path):
        (tmp_path / "rule.yml").write_text("title: Test Rule\nstatus: test")

        with patch("limacharlie.commands.dr.Client") as MockClient, \
             patch("limacharlie.commands.dr.Organization") as MockOrg, \
             patch("limacharlie.commands._dr_convert.ConversionPipeline.convert_all") as mock_convert:
            mock_convert.return_value = [
                ConversionResult(
                    source_path="rule.yml",
                    rule_key="rule",
                    success=True,
                    detect={"event": "NEW_PROCESS"},
                    respond=[{"action": "report", "name": "test"}],
                ),
            ]
            result = self._invoke([
                "--input-dir", str(tmp_path),
                "--dry-run",
            ])

        assert result.exit_code == 0

    def test_output_dir_created(self, tmp_path):
        input_dir = tmp_path / "input"
        input_dir.mkdir()
        (input_dir / "rule.yml").write_text("title: Test")
        output_dir = tmp_path / "output"

        with patch("limacharlie.commands.dr.Client"), \
             patch("limacharlie.commands.dr.Organization"), \
             patch("limacharlie.commands._dr_convert.ConversionPipeline.convert_all") as mock_convert:
            mock_convert.return_value = [
                ConversionResult(
                    source_path="rule.yml",
                    rule_key="rule",
                    success=True,
                    detect={"event": "NEW_PROCESS"},
                    respond=[{"action": "report", "name": "test"}],
                ),
            ]
            self._invoke([
                "--input-dir", str(input_dir),
                "--dry-run",
                "--output-dir", str(output_dir),
            ])

        assert output_dir.exists()
        assert (output_dir / "rule.yaml").exists()
