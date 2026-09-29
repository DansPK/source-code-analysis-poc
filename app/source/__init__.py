"""Loading source code, from a Git URL or a local path."""


class SourceError(Exception):
    """The source could not be loaded. Message is shown to the user as-is."""
