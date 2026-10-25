"""
Unit and Regression Tests for OSIRIS Process Doctor & Fork/Exec Reliability
===========================================================================
"""

import errno
import json
import os
import stat
import subprocess
import tempfile
from pathlib import Path

import pytest

from osiris_cli.command_runner import CommandRunner
from osiris_cli.process_doctor import ProcessDiagnosticReceipt, ProcessDoctor


def test_argv_array_enforcement():
    """Validates that argv MUST be an argument array and never a string."""
    doc = ProcessDoctor()

    with pytest.raises(TypeError, match="argv MUST be an argument array"):
        doc.inspect_command("python3 --version")  # type: ignore

    with pytest.raises(ValueError, match="argv array cannot be empty"):
        doc.inspect_command([])


def test_nonexistent_executable_enoent():
    """Checks that non-existent binary returns ENOENT and can_execute=False."""
    doc = ProcessDoctor()
    receipt = doc.inspect_command(["nonexistent_osiris_binary_xyz123"])

    assert receipt.can_execute is False
    assert receipt.exists is False
    assert receipt.errno_code == errno.ENOENT
    assert receipt.errno_name == "ENOENT"
    assert "not found in PATH" in receipt.error_message
    assert receipt.receipt_hash is not None
    assert len(receipt.receipt_hash) == 64


def test_non_executable_file_eacces():
    """Checks that existing non-executable file returns EACCES."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        non_exec = Path(tmp_dir) / "test_script.sh"
        non_exec.write_text("#!/bin/sh\necho hello\n")
        # Ensure it has no execute permission (rw-r--r--)
        os.chmod(non_exec, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)

        doc = ProcessDoctor(workspace_root=tmp_dir)
        receipt = doc.inspect_command([str(non_exec)], cwd=tmp_dir)

        assert receipt.can_execute is False
        assert receipt.exists is True
        assert receipt.is_file is True
        assert receipt.is_executable is False
        assert receipt.errno_code == errno.EACCES
        assert receipt.errno_name == "EACCES"
        assert "Permission denied" in receipt.error_message


def test_nonexistent_cwd_enoent():
    """Checks that a non-existent working directory triggers ENOENT."""
    doc = ProcessDoctor()
    bad_cwd = "/nonexistent/directory/path/for/osiris_test"
    receipt = doc.inspect_command(["python3", "--version"], cwd=bad_cwd)

    assert receipt.can_execute is False
    assert receipt.errno_code == errno.ENOENT
    assert receipt.errno_name == "ENOENT"
    assert "Working directory does not exist" in receipt.error_message


def test_file_as_cwd_enotdir():
    """Checks that a regular file passed as working directory triggers ENOTDIR."""
    with tempfile.NamedTemporaryFile() as tmp_file:
        doc = ProcessDoctor()
        receipt = doc.inspect_command(["python3", "--version"], cwd=tmp_file.name)

        assert receipt.can_execute is False
        assert receipt.errno_code == errno.ENOTDIR
        assert receipt.errno_name == "ENOTDIR"
        assert "is not a directory" in receipt.error_message


def test_valid_command_preflight_and_execution():
    """Checks that a valid command passes preflight and executes cleanly without shell=True."""
    doc = ProcessDoctor()
    receipt = doc.inspect_command(["python3", "-c", "import sys; sys.stdout.write('OSIRIS_OK')"])

    assert receipt.can_execute is True
    assert receipt.exists is True
    assert receipt.is_file is True
    assert receipt.is_executable is True
    assert receipt.errno_code is None
    assert receipt.path_lookup_success is True
    assert receipt.resolved_executable is not None

    exit_code, stdout, stderr, run_receipt = doc.execute_with_receipt(
        ["python3", "-c", "import sys; sys.stdout.write('OSIRIS_OK')"]
    )
    assert exit_code == 0
    assert stdout == "OSIRIS_OK"
    assert stderr == ""
    assert run_receipt.receipt_hash == receipt.receipt_hash


def test_launch_from_non_project_working_directory():
    """Verifies preflight and execution when launched from /tmp or external directory."""
    with tempfile.TemporaryDirectory() as external_dir:
        doc = ProcessDoctor(workspace_root=external_dir)
        receipt = doc.inspect_command(
            ["python3", "-c", "import os; print(os.getcwd())"],
            cwd=external_dir
        )

        assert receipt.can_execute is True
        assert receipt.cwd == str(Path(external_dir).resolve())

        exit_code, stdout, stderr, _ = doc.execute_with_receipt(
            ["python3", "-c", "import os; print(os.getcwd())"],
            cwd=external_dir
        )
        assert exit_code == 0
        assert stdout.strip() == str(Path(external_dir).resolve())


def test_command_runner_integration_and_receipt():
    """Validates CommandRunner integration with ProcessDoctor and receipts."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        runner = CommandRunner(workspace_root=tmp_dir)

        code, out, err, receipt = runner.run_with_receipt(
            ["python3", "-c", "print('RUNNER_RECEIPT_OK')"],
            cwd=tmp_dir
        )

        assert code == 0
        assert "RUNNER_RECEIPT_OK" in out
        assert receipt.can_execute is True
        assert receipt.receipt_hash is not None
        assert runner.last_receipt is not None
        assert runner.last_receipt.receipt_hash == receipt.receipt_hash
