"""Small explicit contracts prevent unbounded labels and accidental raw-text capture."""
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
import math

Identity = Annotated[str, Field(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_:.\-]+$")]
ModelName = Literal["baseline", "candidate", "popularity", "semantic"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PredictionBody(StrictModel):
    model: ModelName
    user: Annotated[str, Field(pattern=r"^[a-f0-9]{20}$")]
    cohort: Literal["new", "returning"]
    candidate_ids: list[Identity] = Field(min_length=1, max_length=200)
    scores: list[float] = Field(min_length=1, max_length=200)
    event_time: float = Field(ge=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def aligned(self):
        if len(self.candidate_ids) != len(set(self.candidate_ids)) or len(self.scores) != len(self.candidate_ids):
            raise ValueError("Unique candidate identities and aligned scores are required")
        if not all(math.isfinite(v) for v in self.scores):
            raise ValueError("Nonfinite scores are invalid")
        return self


class LabelBody(StrictModel):
    candidate_ids: list[Identity] = Field(min_length=1, max_length=200)
    clicked_ids: list[Identity] = Field(max_length=200)

    @model_validator(mode="after")
    def consistent(self):
        if len(set(self.candidate_ids)) != len(self.candidate_ids) or len(set(self.clicked_ids)) != len(self.clicked_ids):
            raise ValueError("Duplicate candidate/click identities are invalid")
        if not set(self.clicked_ids) <= set(self.candidate_ids):
            raise ValueError("Clicked items must be in the recorded candidate set")
        return self


class PredictionEvent(StrictModel):
    event_id: Identity
    request_id: Identity
    kind: Literal["prediction"]
    body: PredictionBody


class LabelEvent(StrictModel):
    event_id: Identity
    request_id: Identity
    kind: Literal["label"]
    body: LabelBody


Event = Annotated[PredictionEvent | LabelEvent, Field(discriminator="kind")]


class ExperimentRequest(StrictModel):
    scenario: Literal["healthy", "feature_skew", "score_shift", "regression", "missing_feature", "delayed_labels", "sparse_slice", "semantic_ranker"] = "healthy"


class PredictRequest(StrictModel):
    index: int = Field(default=0, ge=0, le=100000)
    model: ModelName = "candidate"


class ModelSpec(StrictModel):
    name: Annotated[str, Field(pattern=r"^[a-z][a-z0-9-]{0,39}$")]
    owner: Annotated[str, Field(min_length=1, max_length=80)]
    task: Literal["ranking"]
    features: list[str]
    protected_slices: list[Literal["new", "returning"]] = ["new", "returning"]
    tolerance: float = Field(default=.025, ge=0, le=.2)
    min_label_coverage: float = Field(default=.8, gt=0, le=1)
    retention_days: int = Field(default=7, ge=1, le=90)

    @model_validator(mode="after")
    def fixed_contract(self):
        from .data import FEATURES
        if self.features != list(FEATURES):
            raise ValueError("Feature order must match the registered serving schema")
        if len(set(self.protected_slices)) != len(self.protected_slices):
            raise ValueError("Protected slices must be unique")
        return self
