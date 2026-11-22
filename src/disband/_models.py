from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

# any string too, for stems, formats and problem types added after this release
StemId = (
    Literal[
        "vocals",
        "vocals.lead",
        "vocals.backing",
        "instrumental",
        "instrumental.drums",
        "instrumental.drums.kick",
        "instrumental.drums.snare",
        "instrumental.drums.toms",
        "instrumental.drums.hihat",
        "instrumental.drums.cymbals",
        "instrumental.drums.other",
        "instrumental.bass",
        "instrumental.guitar",
        "instrumental.piano",
        "instrumental.other",
    ]
    | str
)
Format = Literal["wav", "mp3"] | str
ProblemType = (
    Literal[
        "invalid-request",
        "unauthenticated",
        "out-of-credits",
        "account-suspended",
        "account-locked",
        "not-found",
        "upload-expired",
        "length-required",
        "unsupported-audio",
        "bad-audio",
        "busy",
        "internal",
        "capacity",
        "timeout",
    ]
    | str
)


class Model(BaseModel):
    # fields this release doesn't name are kept, so model_dump gives the API's JSON back whole
    model_config = ConfigDict(frozen=True, extra="allow", use_attribute_docstrings=True)


class StemFile(Model):
    url: str
    bytes: int


class StemFiles(Model):
    """A stem's files, none when it is silent."""

    silent: bool = False
    wav: StemFile | None = None
    mp3: StemFile | None = None


class FieldError(Model):
    path: str
    message: str


class Failure(Model):
    type: ProblemType
    detail: str | None = None


class Problem(Model):
    """RFC 9457 problem details."""

    type: ProblemType
    title: str
    status: int
    detail: str | None = None
    request_id: str
    errors: list[FieldError] = []


class SeparationBase(Model):
    id: str
    name: str | None = None
    created_at: datetime
    expires_at: datetime


class Uploading(SeparationBase):
    status: Literal["uploading"]
    upload_url: str


class Queued(SeparationBase):
    status: Literal["queued"]
    charge: int | None = None
    position: int | None = None
    """The place in line, 1 being next."""


class Processing(SeparationBase):
    status: Literal["processing"]
    charge: int


class Ready(SeparationBase):
    status: Literal["ready"]
    charge: int
    duration: float
    """In seconds."""
    stems: dict[StemId, StemFiles]


class Failed(SeparationBase):
    status: Literal["failed"]
    charge: int
    problem: Failure


Separation = Annotated[Uploading | Queued | Processing | Ready | Failed, Field(discriminator="status")]
Ended = Annotated[Ready | Failed, Field(discriminator="status")]


class SeparationPage(Model):
    separations: list[Separation]
    next: str | None = None


class Stem(Model):
    id: StemId
    name: str
    parent: str


class Catalog(Model):
    stems: list[Stem]


class Credits(Model):
    free: int
    bought: int


class Limits(Model):
    daily: int | None = None
    """Free credits a day, None while free use is paused."""
    seconds: int
    """The longest file, in seconds."""
    bytes: int
    """The largest file, in bytes."""
    jobs: int | None = None
    """Separations at once, None when there is no limit."""
    uploads: int
    """Uploads at once."""


class Usage(Model):
    balance: Credits
    limits: Limits


separation_adapter = TypeAdapter[Separation](Separation)
ended_adapter = TypeAdapter[Ready | Failed](Ended)
