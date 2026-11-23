"""Workbench exceptions carrying actionable advice for the user."""

from __future__ import annotations


class WorkbenchError(Exception):
    """Base class. ``advice`` tells the user how to fix the problem."""

    def __init__(self, message: str, advice: str | None = None):
        super().__init__(message)
        self.message = message
        self.advice = advice

    def __str__(self) -> str:
        if self.advice:
            return f"{self.message}\n  How to fix: {self.advice}"
        return self.message


class UnsupportedFormatError(WorkbenchError):
    pass


class PatternFreeInputError(WorkbenchError):
    """The input has orientation data but no Kikuchi patterns."""


class MissingMetadataError(WorkbenchError):
    pass


class CrystalValidationError(WorkbenchError):
    pass


class MasterPatternError(WorkbenchError):
    pass


class JobCancelled(WorkbenchError):
    pass


class EMsoftError(WorkbenchError):
    pass
