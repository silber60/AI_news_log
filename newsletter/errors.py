"""Pipeline error hierarchy.

Every error carries the pipeline `stage` it belongs to. The CLI reports only
`stage` and the class name, never the message text, because exception text can
carry addresses or other private data (DLVR-06).
"""


class PipelineError(Exception):
    stage: str = "pipeline"


class InvalidWeekError(PipelineError):
    stage = "week"


class FetchError(PipelineError):
    stage = "fetch"


class EmptyFetchError(FetchError):
    stage = "fetch"


class AnalysisInvalid(PipelineError):
    stage = "analyze"


class RenderTooLarge(PipelineError):
    stage = "render"


class NoSubscribersError(PipelineError):
    stage = "deliver"


class DeliveryError(PipelineError):
    stage = "deliver"


class StaleIssueError(PipelineError):
    """A send outside the issue's KST send day, refused before any network call (D-03)."""

    stage = "deliver"
